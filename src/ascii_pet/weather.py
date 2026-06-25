"""Weather API client using OpenWeatherMap."""

import json, time, urllib.request, urllib.error, urllib.parse
from pathlib import Path

from ascii_pet.log import logger

CONFIG_PATH = Path(__file__).parent / 'config' / 'weather.json'
CACHE_SECONDS = 1800  # 30 minutes

_cache = {'data': None, 'time': 0}

def _load_config():
    if CONFIG_PATH.exists():
        return json.load(open(CONFIG_PATH, encoding='utf-8'))
    return {}

def _get_ip_city():
    try:
        req = urllib.request.Request('https://ipapi.co/json/', headers={'User-Agent': 'ascii-pet/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get('city', '')
    except Exception as e:
        logger.debug(f"IP city lookup failed: {e}")
        return ''

def get_weather():
    """Returns dict with keys: temp, description, icon, humidity, wind, city, raw_name. Or None on error."""
    now = time.time()
    if _cache['data'] and now - _cache['time'] < CACHE_SECONDS:
        return _cache['data']

    config = _load_config()
    api_key = config.get('api_key', '')
    if not api_key:
        return None

    city = config.get('city', '') or _get_ip_city()
    if not city:
        return None

    units = config.get('units', 'metric')
    lang = config.get('lang', 'zh_cn')

    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid={api_key}&units={units}&lang={lang}'
        req = urllib.request.Request(url, headers={'User-Agent': 'ascii-pet/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        result = {
            'temp': data['main']['temp'],
            'feels_like': data['main']['feels_like'],
            'humidity': data['main']['humidity'],
            'description': data['weather'][0]['description'],
            'icon': data['weather'][0]['icon'],
            'wind': data['wind']['speed'],
            'raw_name': data['weather'][0]['main'],
            'city': data.get('name', city),
        }
        _cache['data'] = result
        _cache['time'] = now
        return result
    except Exception as e:
        logger.warning(f"Weather API failed for city '{city}': {e}")
        return _cache.get('data')

def format_weather_line(weather):
    """Return a one-line weather summary for display."""
    if not weather:
        return None
    icons = {'01d':'☀️','01n':'🌙','02d':'⛅','02n':'☁️','03d':'☁️','03n':'☁️',
             '04d':'☁️','04n':'☁️','09d':'🌧','09n':'🌧','10d':'🌦','10n':'🌧',
             '11d':'⛈','11n':'⛈','13d':'❄️','13n':'❄️','50d':'🌫','50n':'🌫'}
    icon = icons.get(weather['icon'], '🌍')
    temp = round(weather['temp'])
    return f"{icon} {weather['city']} {temp}° {weather['description']}"
