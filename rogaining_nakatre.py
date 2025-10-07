from flask import Flask, send_file, abort
from PIL import Image
import io
import math
import os

app = Flask(__name__)

# Настройки (измените под вашу карту)
MAP_FILE = 'map.png'  # Путь к вашему PNG-файлу с картой (теперь в repo)
MIN_ZOOM = 10  # Минимальный масштаб (более мелкий; можно скорректировать после расчёта native)
LAT_CENTER = 55.74876  # Широта центра карты
LON_CENTER = 37.61573  # Долгота центра карты
TILE_SIZE = 256
AUTO_CALC_ZOOM = True  # True: авто-расчёт NATIVE_ZOOM по REAL_WIDTH_KM; False: используйте фиксированный ниже
NATIVE_ZOOM_FIXED = 14  # Фиксированный native, если AUTO_CALC_ZOOM=False

# Калибровка по ширине (для точной "Линейки": 1 км = 1 км реальный)
REAL_WIDTH_KM = 5.0  # Реальная ширина области карты в км (горизонталь; измерьте от края до края)
REAL_HEIGHT_KM = None  # Опционально: реальная высота в км (вертикаль; для точности y)


def haversine(lat1, lon1, lat2, lon2):
    """Расстояние в км между двумя точками (haversine)"""
    R = 6371.0  # Радиус Земли
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def lon_to_world(lon, zoom):
    """Мировая x-координата по lon (Web Mercator)"""
    world_size = TILE_SIZE * (1 << zoom)
    return (lon + 180.0) / 360.0 * world_size


def lat_to_world(lat, zoom):
    """Мировая y-координата по lat (Web Mercator, y вниз)"""
    world_size = TILE_SIZE * (1 << zoom)
    lat_rad = math.radians(lat)
    return world_size / 2.0 - world_size / (2.0 * math.pi) * math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))


# Загружаем карту один раз
try:
    map_img = Image.open(MAP_FILE).convert('RGBA')
    map_width, map_height = map_img.size
    print(f"Карта загружена: {map_width}x{map_height} пикселей")
except FileNotFoundError:
    print(f"Ошибка: файл {MAP_FILE} не найден!")
    exit(1)

# Авто-расчёт NATIVE_ZOOM для точного масштаба 1:1 без обрезки
mpp_x = REAL_WIDTH_KM * 1000 / map_width  # м/пиксель по x
ground_mpp_z0_x = 156543.03392 * math.cos(math.radians(LAT_CENTER))  # базовое разрешение z=0
native_zoom_x = math.log2(ground_mpp_z0_x / mpp_x)

if REAL_HEIGHT_KM is not None:
    mpp_y = REAL_HEIGHT_KM * 1000 / map_height  # м/пиксель по y
    ground_mpp_z0_y = 156543.03392  # для y без cos (примерно)
    native_zoom_y = math.log2(ground_mpp_z0_y / mpp_y)
    print(f"z по x: {native_zoom_x:.2f}, z по y: {native_zoom_y:.2f}")
    if abs(native_zoom_x - native_zoom_y) > 1:
        print(f"Предупреждение: aspect distortion >1 z-level; используйте средний")
    native_zoom = round((native_zoom_x + native_zoom_y) / 2)
else:
    native_zoom = round(native_zoom_x)

if AUTO_CALC_ZOOM:
    NATIVE_ZOOM = native_zoom
else:
    NATIVE_ZOOM = NATIVE_ZOOM_FIXED

print(f"Авто-рассчитанный NATIVE_ZOOM: {NATIVE_ZOOM} для {REAL_WIDTH_KM} км на {map_width} px по x")
print(f"Разрешение на native: ~{mpp_x:.2f} м/пиксель (1:1 с линейкой)")

# Рассчитываем мировые координаты rect карты (полное покрытие PNG, scale=1)
world_size_native = TILE_SIZE * (1 << NATIVE_ZOOM)
center_world_x = lon_to_world(LON_CENTER, NATIVE_ZOOM)
center_world_y = lat_to_world(LAT_CENTER, NATIVE_ZOOM)

half_width_units = map_width / 2.0
half_height_units = map_height / 2.0
left_world_x = center_world_x - half_width_units
top_world_y = center_world_y - half_height_units
right_world_x = center_world_x + half_width_units
bottom_world_y = center_world_y + half_height_units

print(
    f"Map rect в world coords (native): x={left_world_x:.0f}..{right_world_x:.0f}, y={top_world_y:.0f}..{bottom_world_y:.0f}")
approx_height_km = haversine(LAT_CENTER + (half_height_units * 156543.03392 / (1 << NATIVE_ZOOM) / 111320), LON_CENTER,
                             LAT_CENTER - (half_height_units * 156543.03392 / (1 << NATIVE_ZOOM) / 111320), LON_CENTER)
print(f"Покрытие: ширина {REAL_WIDTH_KM} км, высота ~{approx_height_km:.1f} км (полная PNG)")


@app.route('/<int:z>/<int:x>/<int:y>.png')
def get_tile(z, x, y):
    if z < MIN_ZOOM or z > NATIVE_ZOOM:
        abort(404)

    # Scale для перевода z-координат в native world coords
    scale = 1 << (NATIVE_ZOOM - z)  # 2**(native - z)

    # Tile rect в native world coords
    tile_left_native = x * TILE_SIZE * scale
    tile_top_native = y * TILE_SIZE * scale
    tile_right_native = (x + 1) * TILE_SIZE * scale
    tile_bottom_native = (y + 1) * TILE_SIZE * scale

    # Пересечение tile rect с map rect
    intersect_left = max(tile_left_native, left_world_x)
    intersect_top = max(tile_top_native, top_world_y)
    intersect_right = min(tile_right_native, right_world_x)
    intersect_bottom = min(tile_bottom_native, bottom_world_y)

    if intersect_left >= intersect_right or intersect_top >= intersect_bottom:
        # Нет пересечения — прозрачный тайл
        trans_img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        img_io = io.BytesIO()
        trans_img.save(img_io, format='PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')

    # Source rect в px карты (native, полное покрытие)
    source_left = intersect_left - left_world_x
    source_top = intersect_top - top_world_y
    source_right = intersect_right - left_world_x
    source_bottom = intersect_bottom - top_world_y
    cropped = map_img.crop((int(source_left), int(source_top), int(source_right), int(source_bottom)))

    # Размер source в native px (для pad)
    source_tile_size = TILE_SIZE * scale
    pad_needed = cropped.width < source_tile_size or cropped.height < source_tile_size

    if pad_needed:
        # Pad прозрачным до полного source размера, с правильным offset'ом
        padded = Image.new('RGBA', (int(source_tile_size), int(source_tile_size)), (0, 0, 0, 0))
        # Offset в tile rect: сколько пропущено слева/сверху до intersect
        offset_left = int(intersect_left - tile_left_native)
        offset_top = int(intersect_top - tile_top_native)
        padded.paste(cropped, (offset_left, offset_top))
        to_resize = padded
    else:
        to_resize = cropped

    # Ресайз до 256x256 (для downscale; на native — identity)
    tile_img = to_resize.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.LANCZOS)

    # Сохраняем
    img_io = io.BytesIO()
    tile_img.save(img_io, format='PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False для production
