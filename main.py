# Farmer and Costing: an offline crop and livestock cost calculator.
import csv
import json
import os
from datetime import datetime

from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivymd.uix.appbar import MDTopAppBar, MDTopAppBarTitle
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.textfield import MDTextField, MDTextFieldHelperText, MDTextFieldHintText


class CostingApp(MDApp):
    title = "Farmer and Costing"
    categories = ("Crop", "Livestock")
    units = ("per kg", "per head", "per crate", "per litre", "per bag")
    presets = (("Chickens", "Livestock"), ("Cattle", "Livestock"), ("Maize", "Crop"), ("Vegetables", "Crop"))

    def build(self):
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.accent_palette = "Amber"
        self.theme_cls.theme_style = "Light"
        self.records = []
        self.category = "Crop"
        self.unit = "per kg"
        self.smart_default_price = ""
        self.data_file = os.path.join(self.user_data_dir, "costings.json")
        self.load_records()

        Window.clearcolor = (0.96, 0.97, 0.94, 1)
        root = MDBoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        with root.canvas.before:
            Color(rgba=(0.96, 0.97, 0.94, 1))
            background = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda instance, value: setattr(background, "pos", value))
        root.bind(size=lambda instance, value: setattr(background, "size", value))

        root.add_widget(MDTopAppBar(MDTopAppBarTitle(text="Farmer and Costing"), type="small",
                                    size_hint_y=None, height=dp(56)))
        root.add_widget(MDLabel(text="Plan costs, revenue and profit for each enterprise.", theme_text_color="Secondary",
                                size_hint_y=None, height=dp(26)))

        content = MDBoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))

        details_card = MDCard(orientation="vertical", padding=dp(12), spacing=dp(8), radius=[dp(8)],
                              size_hint_y=None, height=dp(420), elevation=1)
        details_card.add_widget(MDLabel(text="Enterprise details", font_size=dp(19), size_hint_y=None, height=dp(28)))
        selectors = MDBoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.category_button_text = MDButtonText(text="CATEGORY: CROP")
        self.category_button = MDButton(self.category_button_text, style="outlined")
        self.category_button.bind(on_release=self.open_category_menu)
        self.unit_button_text = MDButtonText(text="UNIT: PER KG")
        self.unit_button = MDButton(self.unit_button_text, style="outlined")
        self.unit_button.bind(on_release=self.open_unit_menu)
        self.preset_button = MDButton(MDButtonText(text="PRESET ITEM"), style="text")
        self.preset_button.bind(on_release=self.open_preset_menu)
        selectors.add_widget(self.category_button)
        selectors.add_widget(self.unit_button)
        selectors.add_widget(self.preset_button)
        details_card.add_widget(selectors)

        form = GridLayout(cols=2, spacing=dp(10), padding=(dp(4), dp(4)), size_hint_y=None, height=dp(330))
        self.inputs = {}
        fields = [("Crop or livestock name", "name", "e.g. Chickens"),
                  ("Seed or feed cost", "seed_cost", "0.00"),
                  ("Labor cost", "labor_cost", "0.00"),
                  ("Other costs", "other_cost", "0.00"),
                  ("Target yield", "yield", "0.00"),
                  ("Expected price", "price", "editable; remembers the latest saved price")]
        for label_text, key, hint in fields:
            field = MDTextField(MDTextFieldHintText(text=label_text),
                                MDTextFieldHelperText(text=hint, mode="on_focus"),
                                mode="outlined", multiline=False)
            self.inputs[key] = field
            form.add_widget(field)
        self.inputs["name"].bind(focus=self.name_focus_changed)
        details_card.add_widget(form)
        content.add_widget(details_card)

        actions_card = MDCard(orientation="vertical", padding=dp(12), spacing=dp(8), radius=[dp(8)],
                              size_hint_y=None, height=dp(116), elevation=1)
        actions_card.add_widget(MDLabel(text="Actions", font_size=dp(17), size_hint_y=None, height=dp(24)))
        actions = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        calculate = MDButton(MDButtonText(text="CALCULATE"), style="filled")
        calculate.bind(on_release=self.calculate)
        save = MDButton(MDButtonText(text="SAVE ENTRY"), style="filled")
        save.bind(on_release=self.save_entry)
        export = MDButton(MDButtonText(text="EXPORT CSV"), style="text")
        export.bind(on_release=self.export_csv)
        actions.add_widget(calculate)
        actions.add_widget(save)
        actions.add_widget(export)
        actions_card.add_widget(actions)
        content.add_widget(actions_card)

        self.result_card = MDCard(orientation="vertical", padding=dp(12), spacing=dp(4), radius=[dp(8)],
                                  size_hint_y=None, height=dp(150), elevation=1)
        self.result = MDLabel(text="Enter values to see the estimate.", theme_text_color="Secondary",
                              valign="top", size_hint_y=None, height=dp(58))
        self.summary_profit = MDLabel(text="Estimated profit/loss: --", font_size=dp(23),
                                      theme_text_color="Custom", text_color=(0.15, 0.45, 0.2, 1),
                                      size_hint_y=None, height=dp(42))
        self.result_card.add_widget(self.summary_profit)
        self.result_card.add_widget(self.result)
        content.add_widget(self.result_card)

        content.add_widget(MDLabel(text="Saved entries", font_size=dp(19), size_hint_y=None, height=dp(34)))
        self.entry_list = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.entry_list.bind(minimum_height=self.entry_list.setter("height"))
        content.add_widget(self.entry_list)
        scroll = ScrollView()
        scroll.add_widget(content)
        root.add_widget(scroll)
        self.refresh_entries()
        return root

    def dropdown(self, caller, values, callback):
        menu = None

        def choose(value):
            callback(value)
            menu.dismiss()

        items = [{"text": value, "on_release": lambda _button, selected=value: choose(selected)}
                 for value in values]
        menu = MDDropdownMenu(caller=caller, items=[
            item for item in items
        ])
        menu.open()

    def open_category_menu(self, button):
        self.dropdown(button, self.categories, self.select_category)

    def open_unit_menu(self, button):
        self.dropdown(button, self.units, self.select_unit)

    def open_preset_menu(self, button):
        self.dropdown(button, [name for name, category in self.presets], self.select_preset)

    def select_category(self, category):
        self.category = category
        self.category_button_text.text = f"CATEGORY: {category.upper()}"

    def select_unit(self, unit):
        self.unit = unit
        self.unit_button_text.text = f"UNIT: {unit.upper()}"

    def select_preset(self, name):
        category = next(category for item, category in self.presets if item == name)
        self.inputs["name"].text = name
        self.select_category(category)
        self.apply_smart_default()

    def name_focus_changed(self, field, focused):
        if not focused:
            self.apply_smart_default()

    def apply_smart_default(self):
        name = self.inputs["name"].text.strip().casefold()
        if not name:
            return
        previous = next((record for record in self.records if record.get("name", "").casefold() == name), None)
        if previous is None:
            return
        price = f"{previous.get('price', 0):.2f}"
        current = self.inputs["price"].text.strip()
        if not current or current == self.smart_default_price:
            self.inputs["price"].text = price
            self.smart_default_price = price
            self.result.text = f"Latest saved price loaded for {previous['name']}. You can edit it for today's market."

    def number(self, key):
        try:
            value = float(self.inputs[key].text.strip() or 0)
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            raise ValueError(f"{key.replace('_', ' ').title()} must be a non-negative number.")

    def calculate_values(self):
        expenses = self.number("seed_cost") + self.number("labor_cost") + self.number("other_cost")
        revenue = self.number("yield") * self.number("price")
        profit = revenue - expenses
        margin = (profit / revenue * 100) if revenue else 0
        return expenses, revenue, profit, margin

    def calculate(self, *_):
        try:
            expenses, revenue, profit, margin = self.calculate_values()
            self.show_summary(expenses, revenue, profit, margin)
        except ValueError as error:
            self.result.text = str(error)

    def show_summary(self, expenses, revenue, profit, margin):
        self.result.text = (f"Total cost: {expenses:,.2f}\nExpected revenue: {revenue:,.2f}\n"
                            f"Profit margin: {margin:.1f}%")
        self.summary_profit.text = f"Estimated profit/loss: {profit:,.2f}"
        self.summary_profit.text_color = (0.15, 0.55, 0.25, 1) if profit >= 0 else (0.75, 0.15, 0.12, 1)

    def save_entry(self, *_):
        name = self.inputs["name"].text.strip()
        if not name:
            self.result.text = "Enter a crop or livestock name before saving."
            return
        try:
            expenses, revenue, profit, margin = self.calculate_values()
        except ValueError as error:
            self.result.text = str(error)
            return
        record = {key: self.number(key) for key in ("seed_cost", "labor_cost", "other_cost", "yield", "price")}
        record.update({"name": name, "category": self.category, "unit": self.unit, "expenses": expenses,
                       "revenue": revenue, "profit": profit, "margin": margin,
                       "saved_at": datetime.now().isoformat(timespec="seconds")})
        self.records.insert(0, record)
        self.persist_records()
        self.refresh_entries()
        self.smart_default_price = f"{record['price']:.2f}"
        self.show_summary(expenses, revenue, profit, margin)
        self.result.text = f"Saved {name}. Latest price will be suggested next time."

    def load_records(self):
        try:
            with open(self.data_file, "r", encoding="utf-8") as data:
                self.records = json.load(data)
        except (OSError, ValueError):
            self.records = []

    def persist_records(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as data:
            json.dump(self.records, data, indent=2)

    def refresh_entries(self):
        if not hasattr(self, "entry_list"):
            return
        self.entry_list.clear_widgets()
        for record in self.records:
            category = record.get("category", "Crop")
            unit = record.get("unit", "per kg")
            card = MDCard(orientation="vertical", padding=dp(10), radius=[dp(6)], size_hint_y=None, height=dp(82), elevation=1)
            text = (f"{record['name']}  |  {category}  |  {unit}\n"
                    f"Cost {record['expenses']:,.2f}  |  Revenue {record['revenue']:,.2f}  |  Profit {record['profit']:,.2f}")
            card.add_widget(MDLabel(text=text, theme_text_color="Primary"))
            self.entry_list.add_widget(card)

    def export_csv(self, *_):
        path = os.path.join(self.user_data_dir, "costings.csv")
        columns = ["name", "category", "unit", "seed_cost", "labor_cost", "other_cost", "yield", "price",
                   "expenses", "revenue", "profit", "margin", "saved_at"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as data:
                writer = csv.DictWriter(data, fieldnames=columns)
                writer.writeheader()
                writer.writerows(self.records)
            self.result.text = f"Exported {len(self.records)} entries to:\n{path}"
        except OSError as error:
            self.result.text = f"Could not export CSV: {error}"


if __name__ == "__main__":
    CostingApp().run()
