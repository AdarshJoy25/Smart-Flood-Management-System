# flood_kivy_app_no_number.py
# Flood Guard app without phone number; offline alerts per city

import kivy
kivy.require('2.1.0')

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty

import json, os, requests, threading, time, random
from datetime import datetime

try:
    from plyer import tts as plyer_tts
except:
    plyer_tts = None

try:
    from plyer import gps as plyer_gps
except:
    plyer_gps = None

try:
    import pyttsx3
except:
    pyttsx3 = None

# ---------------- CONFIG ---------------- #
API_KEY = "b41f2c73b618550863cd04435a6af6be"
CACHE_FILE = "weather_cache.json"
CHECKLIST_FILE = "checklist.json"
OFFLINE_ALERT_FILE = "offline_alert.json"  # now city-based offline alerts

CHECKLIST_ITEMS = [
    "Drinking Water", "Torch & Batteries", "First Aid Kit",
    "Dry Food", "Important Documents", "Power Bank"
]

FLOOD_THRESHOLD_RAIN = 100  # mm threshold

# ---------------- HELPER FUNCTIONS ---------------- #
def load_checklist():
    if os.path.exists(CHECKLIST_FILE):
        try:
            with open(CHECKLIST_FILE, "r") as f:
                return json.load(f)
        except:
            return {item: False for item in CHECKLIST_ITEMS}
    return {item: False for item in CHECKLIST_ITEMS}

def save_checklist(state):
    with open(CHECKLIST_FILE, "w") as f:
        json.dump(state, f)

def fetch_weather(city):
    if not city:
        return load_cached_weather("Unknown")
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={requests.utils.quote(city)}&appid={API_KEY}&units=metric"
        response = requests.get(url, timeout=6)
        data = response.json()
        if data.get("cod") == 200:
            info = {
                "time": datetime.now().strftime("%d-%m-%Y %I:%M %p"),
                "description": data["weather"][0]["description"].capitalize(),
                "temp": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "wind": data["wind"]["speed"],
                "rain": data.get("rain", {}).get("1h", 0),
                "city": city
            }
            cache = {}
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r") as f:
                        cache = json.load(f)
                except:
                    cache = {}
            cache[city] = info
            with open(CACHE_FILE, "w") as f:
                json.dump(cache, f, indent=2)
            return info
        else:
            return load_cached_weather(city)
    except:
        return load_cached_weather(city)

def load_cached_weather(city):
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
                if city in cache:
                    return cache[city]
        except:
            pass
    return {
        "time": "No cached data",
        "description": "Unavailable",
        "temp": "-",
        "humidity": "-",
        "wind": "-",
        "rain": 0,
        "city": city or "Unknown"
    }

def check_internet():
    for url in ["https://www.google.com", "https://api.openweathermap.org"]:
        try:
            requests.get(url, timeout=5)
            return True
        except:
            continue
    return False

def platform_speak(text):
    if not text:
        return
    try:
        if plyer_tts is not None:
            try:
                plyer_tts.speak(text)
                return
            except:
                pass
    except:
        pass
    try:
        if pyttsx3 is not None:
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.say(text)
            engine.runAndWait()
            return
    except:
        pass
    print("TTS:", text)

def detect_city_gps_then_ip(timeout=6):
    if plyer_gps is not None:
        gps_result = {}
        event = threading.Event()
        def gps_location(**kwargs):
            try:
                lat = kwargs.get('lat') or kwargs.get('latitude')
                lon = kwargs.get('lon') or kwargs.get('longitude')
                if lat and lon:
                    gps_result['lat'] = float(lat)
                    gps_result['lon'] = float(lon)
                    event.set()
            except:
                pass
        try:
            plyer_gps.configure(on_location=gps_location, on_status=lambda *a: None)
            plyer_gps.start(minTime=1000, minDistance=0)
            got = event.wait(timeout)
            try:
                plyer_gps.stop()
            except:
                pass
            if got and 'lat' in gps_result:
                lat, lon = gps_result['lat'], gps_result['lon']
                try:
                    url = f"http://ip-api.com/json/{lat},{lon}"
                    r = requests.get(url, timeout=6).json()
                    if r.get('status') == 'success':
                        return r.get('city')
                except:
                    pass
        except:
            pass
    try:
        r = requests.get("http://ip-api.com/json/", timeout=6).json()
        if r.get("status") == "success":
            return r.get("city")
    except:
        pass
    return None

# ---------------- SERVER SIMULATION ---------------- #
def simulate_server(app):
    while True:
        city = app.user_city or "Unknown"
        weather = fetch_weather(city)
        rain = weather.get("rain", 0)
        if rain >= FLOOD_THRESHOLD_RAIN:
            alert = f"⚠️ Flood Alert in {city}! Rain: {rain} mm. Stay Safe!"
        else:
            if random.randint(0, 10) > 8:
                alert = f"⚠️ Flood Alert in {city}! Heavy rain expected! Stay Safe!"
            else:
                alert = f"No flood risk in {city}."
        try:
            with open(OFFLINE_ALERT_FILE, "w") as f:
                json.dump({"alert": alert}, f, indent=2)
        except:
            pass
        time.sleep(20)

# ---------------- KIVY SCREENS ---------------- #
class MainScreen(Screen):
    city_input = ObjectProperty(None)
    status_label = ObjectProperty(None)
    flood_label = ObjectProperty(None)
    weather_label = ObjectProperty(None)
    offline_button = ObjectProperty(None)

    def on_pre_enter(self):
        app = App.get_running_app()
        self.city_input.text = app.user_city or ""
        self.update_status_label()
        self.update_weather_display()
        self.update_flood_label()

    def update_status_label(self):
        app = App.get_running_app()
        self.status_label.text = f"Status: {'Online' if app.online else 'Offline'}"
        self.offline_button.opacity = 0 if app.online else 1
        self.offline_button.disabled = app.online

    def update_weather_display(self):
        app = App.get_running_app()
        w = app.weather_data
        if w:
            self.weather_label.text = (f"City: {w.get('city')}\n"
                                       f"Desc: {w.get('description')}\n"
                                       f"Temp: {w.get('temp')}°C\n"
                                       f"Hum: {w.get('humidity')}%\n"
                                       f"Rain(1h): {w.get('rain')} mm")
        else:
            self.weather_label.text = "No weather data."

    def on_update_weather(self):
        app = App.get_running_app()
        new_city = self.city_input.text.strip()
        if not new_city:
            Popup(title="Error", content=Label(text="Please enter a city."), size_hint=(.7, .3)).open()
            return
        app.user_city = new_city
        app.update_weather()
        self.update_weather_display()
        self.update_flood_label()

    def on_show_checklist(self):
        app = App.get_running_app()
        checklist_state = app.checklist_state
        layout = GridLayout(cols=1, spacing=8, padding=8)
        boxes = {}
        from kivy.uix.checkbox import CheckBox
        for item in CHECKLIST_ITEMS:
            row = BoxLayout(size_hint_y=None, height=40, spacing=8)
            cb = CheckBox(active=checklist_state.get(item, False))
            lbl = Label(text=item)
            row.add_widget(cb)
            row.add_widget(lbl)
            layout.add_widget(row)
            boxes[item] = cb

        def save_close(instance):
            for k, cb in boxes.items():
                checklist_state[k] = bool(cb.active)
            save_checklist(checklist_state)
            popup.dismiss()

        btn = Button(text="Save", size_hint_y=None, height=40)
        btn.bind(on_release=save_close)
        layout.add_widget(btn)
        popup = Popup(title="Preparedness Checklist", content=layout, size_hint=(.9, .9))
        popup.open()

    def on_show_instructions(self):
        tips = ("Flood Safety Instructions:\n"
                "1. Move to higher ground.\n"
                "2. Turn off electricity and gas.\n"
                "3. Do not walk or drive through flood waters.\n"
                "4. Keep emergency kit ready.\n"
                "5. Listen to local authorities for evacuation orders.")
        Popup(title="Instructions", content=Label(text=tips), size_hint=(.9, .7)).open()

    def on_show_contacts(self):
        contacts = {"Police": "100", "Ambulance": "108", "Fire": "101", "Disaster Helpline": "1078"}
        layout = GridLayout(cols=1, spacing=6, padding=6)
        for name, number in contacts.items():
            layout.add_widget(Label(text=f"{name}: {number}"))
        Popup(title="Emergency Contacts", content=layout, size_hint=(.8, .6)).open()

    def on_offline_tts(self):
        app = App.get_running_app()
        alert = app.get_offline_alert()
        platform_speak(alert)

    def update_flood_label(self):
        app = App.get_running_app()
        app.flood_risk = app.analyze_flood_risk(app.weather_data or {})
        if app.flood_risk:
            self.flood_label.text = "⚠️ Flood Risk Detected! Stay Alert!"
            if not app.online:
                platform_speak(app.get_offline_alert())
        else:
            self.flood_label.text = "No flood risk currently."

# ---------------- APP ---------------- #
class FloodKivyApp(App):
    user_city = StringProperty("Unknown")
    online = BooleanProperty(False)
    weather_data = ObjectProperty(None)
    checklist_state = ObjectProperty({})

    def build(self):
        self.title = "FLOOD GUARD"
        self.checklist_state = load_checklist()
        self.online = check_internet()

        city = None
        try:
            city = detect_city_gps_then_ip(timeout=6)
        except:
            pass
        if city:
            self.user_city = city

        self.weather_data = fetch_weather(self.user_city or "")

        # start server simulator thread
        threading.Thread(target=simulate_server, args=(self,), daemon=True).start()

        # Build main screen
        sm = ScreenManager(transition=FadeTransition())
        main = MainScreen(name="main")

        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=8)
        main_layout.add_widget(Label(text="FLOOD GUARD", font_size='20sp', size_hint=(1, .12)))

        status_lbl = Label(text=f"Status: {'Online' if self.online else 'Offline'}", size_hint=(1, .06))
        main.status_label = status_lbl
        main_layout.add_widget(status_lbl)

        city_row = BoxLayout(size_hint=(1, .08))
        city_row.add_widget(Label(text="Enter Your City:", size_hint=(.45, 1)))
        city_input = TextInput(text=self.user_city, multiline=False, size_hint=(.55, 1))
        main.city_input = city_input
        city_row.add_widget(city_input)
        main_layout.add_widget(city_row)

        update_btn = Button(text="Update Weather", size_hint=(1, .08))
        update_btn.bind(on_release=lambda inst: main.on_update_weather())
        main_layout.add_widget(update_btn)

        flood_lbl = Label(text="", size_hint=(1, .12), color=(1,0,0,1))
        main.flood_label = flood_lbl
        main_layout.add_widget(flood_lbl)

        weather_lbl = Label(text="", size_hint=(1, .25))
        main.weather_label = weather_lbl
        main_layout.add_widget(weather_lbl)

        btns = GridLayout(cols=1, size_hint=(1, .4), spacing=8)
        c_btn = Button(text="Checklist")
        c_btn.bind(on_release=lambda inst: main.on_show_checklist())
        btns.add_widget(c_btn)

        i_btn = Button(text="Instructions")
        i_btn.bind(on_release=lambda inst: main.on_show_instructions())
        btns.add_widget(i_btn)

        offline_btn = Button(text="Speak Offline Alert")
        offline_btn.bind(on_release=lambda inst: main.on_offline_tts())
        main.offline_button = offline_btn
        if self.online:
            offline_btn.opacity = 0
            offline_btn.disabled = True
        btns.add_widget(offline_btn)

        contacts_btn = Button(text="Emergency Contacts")
        contacts_btn.bind(on_release=lambda inst: main.on_show_contacts())
        btns.add_widget(contacts_btn)

        main_layout.add_widget(btns)
        main.add_widget(main_layout)
        sm.add_widget(main)

        # schedule periodic tasks
        Clock.schedule_interval(lambda dt: self.schedule_status_check(), 10)
        Clock.schedule_interval(lambda dt: self.schedule_weather_update(), 300)
        Clock.schedule_interval(lambda dt: self.update_flood_label(), 60)

        return sm

    def update_weather(self):
        main_screen = self.root.get_screen("main")
        new_city = main_screen.city_input.text.strip()
        if new_city:
            self.user_city = new_city
            self.weather_data = fetch_weather(self.user_city)
            self.flood_risk = self.analyze_flood_risk(self.weather_data)
            main_screen.update_weather_display()

    def analyze_flood_risk(self, weather):
        rain = 0
        try:
            rain = weather.get("rain", 0) if weather else 0
        except:
            rain = 0
        return (rain >= FLOOD_THRESHOLD_RAIN)

    def update_flood_label(self):
        try:
            main = self.root.get_screen("main")
        except:
            return
        self.flood_risk = self.analyze_flood_risk(self.weather_data or {})
        if self.flood_risk:
            main.flood_label.text = "⚠️ Flood Risk Detected! Stay Alert!"
            if not self.online:
                platform_speak(self.get_offline_alert())
        else:
            main.flood_label.text = "No flood risk currently."

    def get_offline_alert(self):
        if os.path.exists(OFFLINE_ALERT_FILE):
            try:
                with open(OFFLINE_ALERT_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("alert", "No new alerts.")
            except:
                return "No new alerts."
        return "No new alerts."

    def schedule_status_check(self):
        new_status = check_internet()
        if new_status != self.online:
            self.online = new_status
            try:
                ms = self.root.get_screen("main")
                ms.update_status_label()
            except:
                pass
        return True

    def schedule_weather_update(self):
        if self.online:
            self.weather_data = fetch_weather(self.user_city or "")
            self.flood_risk = self.analyze_flood_risk(self.weather_data)
            try:
                ms = self.root.get_screen("main")
                ms.update_weather_display()
            except:
                pass
        return True

if __name__ == '__main__':
    FloodKivyApp().run()
