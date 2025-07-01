from flask import Flask, send_file, abort
import os
import requests

app = Flask(__name__)
CACHE_DIR = "cache"

# Создаем папку кеша, если нет
os.makedirs(CACHE_DIR, exist_ok=True)

COOKIE = {'uid': 'AAAAEWg1iHsI3zABAwOuAg=='}
HEADERS = {
    'Referer': 'https://nakarte.me/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'ru,en;q=0.9',
    'Connection': 'keep-alive',
}

def tile_path(z, x, y):
    return os.path.join(CACHE_DIR, f"{z}_{x}_{y}.png")

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def proxy_tile(z, x, y):
    path = tile_path(z, x, y)
    if os.path.isfile(path):
        # Если тайл есть в кэше — отдаем его
        return send_file(path, mimetype='image/png')

    # Иначе скачиваем тайл
    url = f'https://proxy.nakarte.me/http/nakartetiles.s3-website.eu-central-1.amazonaws.com/{z}/{x}/{y}.png'
    try:
        resp = requests.get(url, cookies=COOKIE, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        # Сохраняем в кэш
        with open(path, 'wb') as f:
            f.write(resp.content)
        return send_file(path, mimetype='image/png')
    except requests.RequestException as e:
        abort(404, description=f"Tile not found: {e}")

if __name__ == '__main__':
    # Делаем сервер доступным в локальной сети
    app.run(host='0.0.0.0', port=5000)