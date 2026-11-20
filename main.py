import datetime
import math
import urllib.request
import urllib.parse
import json
import ephem
from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.camera import Camera
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from plyer import gps, compass, accelerometer

# Trackable solar system bodies & bright stars for local "When can I see this?" calculations
TRACKABLE_OBJECTS = {
    "moon": ("Moon", ephem.Moon),
    "mercury": ("Mercury", ephem.Mercury),
    "venus": ("Venus", ephem.Venus),
    "mars": ("Mars", ephem.Mars),
    "jupiter": ("Jupiter", ephem.Jupiter),
    "saturn": ("Saturn", ephem.Saturn),
    "uranus": ("Uranus", ephem.Uranus),
    "neptune": ("Neptune", ephem.Neptune),
    "sirius": ("Sirius", lambda: ephem.star("Sirius")),
    "betelgeuse": ("Betelgeuse", lambda: ephem.star("Betelgeuse")),
    "orion": ("Betelgeuse (Orion)", lambda: ephem.star("Betelgeuse")),
    "vega": ("Vega", lambda: ephem.star("Vega")),
    "polaris": ("Polaris", lambda: ephem.star("Polaris")),
    "rigel": ("Rigel", lambda: ephem.star("Rigel")),
    "aldebaran": ("Aldebaran", lambda: ephem.star("Aldebaran")),
    "antares": ("Antares", lambda: ephem.star("Antares")),
    "spica": ("Spica", lambda: ephem.star("Spica")),
    "altair": ("Altair", lambda: ephem.star("Altair")),
    "capella": ("Capella", lambda: ephem.star("Capella")),
}

class StarGazerApp(App):
    def build(self):
        self.lat = '28.50'   # Default latitude until GPS locks
        self.lon = '77.20'   # Default longitude until GPS locks
        self.last_answer = ""
        self.search_open = False

        self.root_layout = FloatLayout()

        # 1. LIVE CAMERA BACKGROUND
        try:
            self.cam = Camera(play=True, resolution=(640, 480), allow_stretch=True, keep_ratio=False)
            self.root_layout.add_widget(self.cam)
        except Exception:
            self.root_layout.add_widget(Label(text="[Live Sky Camera View]", pos_hint={'center_x': 0.5, 'center_y': 0.6}))

        # 2. TOP BAR: Magnifying Glass Icon (Upper-Left) + GPS Permission Button (Upper-Right)
        top_bar = BoxLayout(size_hint=(0.96, 0.09), pos_hint={'center_x': 0.5, 'top': 0.99}, spacing=8)

        self.mag_btn = Button(
            text="🔍",
            font_size='24sp',
            size_hint=(0.15, 1),
            background_normal='',
            background_color=(0.1, 0.15, 0.25, 0.9)
        )
        self.mag_btn.bind(on_press=self.toggle_space_search)

        self.status_lbl = Label(text="Tap 'Allow GPS' to track sky", font_size='14sp')

        perm_btn = Button(
            text="Allow GPS",
            size_hint=(0.28, 1),
            background_normal='',
            background_color=(0.1, 0.65, 0.35, 0.9)
        )
        perm_btn.bind(on_press=self.enable_sensors)

        top_bar.add_widget(self.mag_btn)
        top_bar.add_widget(self.status_lbl)
        top_bar.add_widget(perm_btn)
        self.root_layout.add_widget(top_bar)

        # 3. POP-DOWN UNIVERSAL SPACE SEARCH BAR (Hidden until 🔍 is clicked)
        self.space_search_bar = BoxLayout(
            size_hint=(0.96, 0.09),
            pos_hint={'center_x': 0.5, 'top': 0.89},
            spacing=8,
            opacity=0,
            disabled=True
        )
        self.space_query_input = TextInput(
            hint_text="Ask anything about space or 'When can I see...?'",
            multiline=False,
            font_size='15sp'
        )
        self.space_query_input.bind(on_text_validate=self.search_anything_in_space)

        space_go_btn = Button(
            text="Ask Space",
            size_hint=(0.26, 1),
            background_normal='',
            background_color=(0.45, 0.25, 0.85, 0.95)
        )
        space_go_btn.bind(on_press=self.search_anything_in_space)

        self.space_search_bar.add_widget(self.space_query_input)
        self.space_search_bar.add_widget(space_go_btn)
        self.root_layout.add_widget(self.space_search_bar)

        # 4. SCROLLABLE DETAILED ANSWER DISPLAY
        scroll = ScrollView(size_hint=(0.94, 0.43), pos_hint={'center_x': 0.5, 'y': 0.22})
        self.answer_lbl = Label(
            text="Point at the sky & tap ➤, or tap 🔍 at top-left to ask anything about space!",
            font_size='16sp',
            markup=True,
            size_hint_y=None,
            halign='left',
            valign='top'
        )
        self.answer_lbl.bind(width=lambda *x: self.answer_lbl.setter('text_size')(self.answer_lbl, (self.answer_lbl.width, None)))
        self.answer_lbl.bind(texture_size=lambda *x: self.answer_lbl.setter('height')(self.answer_lbl, self.answer_lbl.texture_size))
        scroll.add_widget(self.answer_lbl)
        self.root_layout.add_widget(scroll)

        # 5. SAVE BUTTON
        save_btn = Button(
            text="Save Answer",
            size_hint=(0.36, 0.07),
            pos_hint={'center_x': 0.5, 'y': 0.13},
            background_normal='',
            background_color=(0.2, 0.25, 0.35, 0.9)
        )
        save_btn.bind(on_press=self.save_sighting)
        self.root_layout.add_widget(save_btn)

        # 6. BOTTOM CAMERA-SKY QUESTION BAR WITH BLUE PAPER-PLANE SEND ICON (➤)
        ask_bar = BoxLayout(size_hint=(0.96, 0.09), pos_hint={'center_x': 0.5, 'y': 0.02}, spacing=8)
        self.sky_input = TextInput(
            hint_text="Ask: Which planet, star, or constellation is here?",
            multiline=False,
            font_size='15sp'
        )
        self.sky_input.bind(on_text_validate=self.identify_camera_sky)

        send_btn = Button(
            text="➤",
            font_size='28sp',
            size_hint=(0.18, 1),
            background_normal='',
            background_color=(0.05, 0.52, 0.98, 1)  # Bright Blue Paper-Plane Button
        )
        send_btn.bind(on_press=self.identify_camera_sky)

        ask_bar.add_widget(self.sky_input)
        ask_bar.add_widget(send_btn)
        self.root_layout.add_widget(ask_bar)

        return self.root_layout

    # --- TOGGLE MAGNIFYING GLASS SEARCH BAR ---
    def toggle_space_search(self, instance):
        self.search_open = not self.search_open
        if self.search_open:
            self.space_search_bar.opacity = 1
            self.space_search_bar.disabled = False
            self.space_query_input.focus = True
        else:
            self.space_search_bar.opacity = 0
            self.space_search_bar.disabled = True

    # --- ASK ANYTHING ABOUT ANYTHING IN SPACE + LOCAL VISIBILITY ---
    def search_anything_in_space(self, instance):
        query = self.space_query_input.text.strip()
        if not query:
            self.answer_lbl.text = "Ask anything! Example: 'Black holes', 'Andromeda Galaxy', 'James Webb', or 'When can I see Saturn?'"
            return

        self.answer_lbl.text = "Searching space database..."
        q_lower = query.lower()
        output_parts = [f"[b][color=#66b3ff]Space Query: {query}[/color][/b]\n\n"]

        # 1. Check if the question mentions any trackable planet or bright star for local sky visibility
        matched_obj = None
        for key, (obj_name, obj_factory) in TRACKABLE_OBJECTS.items():
            if key in q_lower:
                matched_obj = (obj_name, obj_factory())
                break

        if matched_obj:
            obj_name, body = matched_obj
            observer = ephem.Observer()
            observer.lat = self.lat
            observer.lon = self.lon
            observer.date = datetime.datetime.utcnow()
            body.compute(observer)

            alt_deg = math.degrees(body.alt)
            az_deg = math.degrees(body.az)
            constellation = ephem.constellation(body)

            if alt_deg > 0:
                output_parts.append(
                    f"[b][color=#66ff99]Visibility From Your Area Right Now:[/color][/b]\n"
                    f"• [b]Status:[/b] Visible in the sky right now!\n"
                    f"• [b]Where to Look:[/b] {self.az_to_compass(az_deg)} ({az_deg:.0f}°), "
                    f"{alt_deg:.0f}° above the horizon (in {constellation}).\n\n"
                )
            else:
                next_rise_utc = observer.next_rising(body).datetime()
                local_rise = next_rise_utc + datetime.timedelta(hours=5, minutes=30)
                output_parts.append(
                    f"[b][color=#ffcc66]Visibility From Your Area:[/color][/b]\n"
                    f"• [b]Status:[/b] Currently below your horizon.\n"
                    f"• [b]Next Rise Time:[/b] {local_rise.strftime('%d %b %Y at %I:%M %p')} (Local Time)\n"
                    f"• [b]Constellation:[/b] {constellation}\n\n"
                )
        elif "when" in q_lower and ("see" in q_lower or "visible" in q_lower):
            output_parts.append(
                f"[b][color=#ffcc66]Visibility Tip:[/color][/b] Deep-sky objects (galaxies, nebulae, black holes) "
                f"are best seen after sunset away from city lights using binoculars or a telescope.\n\n"
            )

        # 2. Universal Space Search via Wikipedia Smart Search API (Answers ANY question about space!)
        clean_topic = q_lower
        for phrase in ["when can i see", "when will i see", "what is a", "what is", "tell me about", "who discovered", "how do", "explain"]:
            clean_topic = clean_topic.replace(phrase, "")
        clean_topic = clean_topic.replace("?", "").strip() or query

        try:
            headers = {'User-Agent': 'StarGazerARApp/1.0 (Educational)'}
            # Step A: Search Wikipedia for the closest matching space article title
            search_url = f"https://wikipedia.org{urllib.parse.quote(clean_topic + ' astronomy space')}&limit=1&format=json"
            req1 = urllib.request.Request(search_url, headers=headers)
