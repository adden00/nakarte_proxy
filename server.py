from flask import Flask, request, Response
import requests

app = Flask(__name__)

COOKIE = {'uid': 'AAAAEWg1iHsI3zABAwOuAg=='}
HEADERS = {
    'Referer': 'https://nakarte.me/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'ru,en;q=0.9',
    'Connection': 'keep-alive',
}

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def proxy_tile(z, x, y):
    url = f'https://proxy.nakarte.me/http/nakartetiles.s3-website.eu-central-1.amazonaws.com/{z}/{x}/{y}.png'
    try:
        resp = requests.get(url, cookies=COOKIE, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return Response(resp.content, content_type=resp.headers.get('Content-Type', 'image/png'))
    except requests.RequestException as e:
        return f"Error fetching tile: {e}", 500

if __name__ == '__main__':
    app.run(port=5000)