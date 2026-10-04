# Farmer and Costing: an offline farm manager (costing, money, livestock, crops, stock, tasks, calculators).
import csv
import io
import json
import math
import os
from datetime import datetime, timedelta

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.utils import escape_markup, platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.textfield import MDTextField, MDTextFieldHelperText, MDTextFieldHintText

DATE_FMT = "%Y-%m-%d"
GREEN = (0.18, 0.49, 0.20, 1)
OK = (0.15, 0.55, 0.25, 1)
RED = (0.75, 0.15, 0.12, 1)
AMBER = (0.80, 0.47, 0.0, 1)
MUTED = (0.38, 0.42, 0.38, 1)
DARK = (0.12, 0.15, 0.12, 1)
WHITE = (1, 1, 1, 1)
PAGE_BG = (0.96, 0.97, 0.94, 1)

GESTATION = {"Cattle": 283, "Goats": 150, "Sheep": 147, "Pigs": 114, "Horses": 340,
             "Rabbits": 31, "Chickens": 21, "Ducks": 28, "Other": 0}
SPECIES = ("Cattle", "Goats", "Sheep", "Pigs", "Chickens", "Ducks", "Rabbits", "Horses", "Bees", "Other")


# ---------------------------------------------------------------- small helpers
def today():
    return datetime.now().date()


def parse_date(text):
    try:
        return datetime.strptime(str(text).strip(), DATE_FMT).date()
    except (ValueError, TypeError):
        return None


def days_until(text):
    d = parse_date(text)
    return None if d is None else (d - today()).days


def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_num(value):
    try:
        return f"{float(value):.2f}".rstrip("0").rstrip(".") or "0"
    except (TypeError, ValueError):
        return str(value)


def days_text(n):
    if n is None:
        return ""
    if n < 0:
        return f"{-n} d overdue"
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    return f"in {n} d"


def paint(widget, rgba, radius=0):
    with widget.canvas.before:
        Color(*rgba)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    widget.bind(pos=lambda i, v: setattr(rect, "pos", v), size=lambda i, v: setattr(rect, "size", v))


def F(key, label, kind="text", **kw):
    field = {"k": key, "l": label, "t": kind}
    field.update(kw)
    return field


class Row(ButtonBehavior, MDBoxLayout):
    pass


class Scrim(ButtonBehavior, Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        paint(self, (0, 0, 0, 0.45))


class Panel(MDBoxLayout):
    def on_touch_down(self, touch):
        super().on_touch_down(touch)
        return self.collide_point(*touch.pos)


# ---------------------------------------------------------------- record modules
LEDGER_CATS = ("Sales - crops", "Sales - livestock", "Sales - produce", "Grant / subsidy", "Other income",
               "Seed", "Feed", "Fertiliser", "Chemicals", "Labour", "Fuel", "Vet & medicine", "Repairs",
               "Transport", "Equipment", "Rent & lease", "Utilities", "Insurance", "Loan repayment",
               "Other expense")


def breeding_due(r):
    d = parse_date(r.get("mated"))
    days = int(num(r.get("days"))) or GESTATION.get(r.get("species"), 0)
    return None if d is None or not days else d + timedelta(days=days)


def view_ledger(a, r):
    income = r.get("kind") == "Income"
    title = f"{'+' if income else '-'}{a.money(num(r.get('amount')))}   {r.get('category', '')}"
    detail = r.get("date", "")
    if r.get("description"):
        detail += f"  |  {r['description']}"
    return title, [detail], (OK if income else RED)


def sum_ledger(a):
    mi, me = a.ledger_totals(a.month_key())
    ai, ae = a.ledger_totals()
    lines = [f"This month:  income {a.money(mi)}  |  expenses {a.money(me)}",
             f"Net this month: {a.money(mi - me)}",
             f"All time:  income {a.money(ai)}  |  expenses {a.money(ae)}  |  net {a.money(ai - ae)}"]
    cats = {}
    for r in a.db["ledger"]:
        if r.get("kind") != "Income":
            cats[r.get("category", "")] = cats.get(r.get("category", ""), 0) + num(r.get("amount"))
    if cats:
        top = max(cats, key=cats.get)
        lines.append(f"Biggest cost: {top} ({a.money(cats[top])})")
    return lines


def view_livestock(a, r):
    lines = [f"{r.get('species', '')}" + (f"  |  {r['breed']}" if r.get("breed") else "")]
    if r.get("acquired"):
        lines.append(f"Since {r['acquired']}")
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{r.get('name', '')}  x{int(num(r.get('count')))}", lines, None


def sum_livestock(a):
    totals = {}
    for r in a.db["livestock"]:
        totals[r.get("species", "Other")] = totals.get(r.get("species", "Other"), 0) + int(num(r.get("count")))
    if not totals:
        return []
    return ["  |  ".join(f"{s}: {n}" for s, n in sorted(totals.items())), f"Total head: {sum(totals.values())}"]


def view_health(a, r):
    lines = [r.get("date", "")]
    color = None
    if r.get("next_due"):
        n = days_until(r["next_due"])
        lines.append(f"Next due {r['next_due']} ({days_text(n)})")
        color = RED if n is not None and n < 0 else AMBER if n is not None and n <= 7 else None
    if num(r.get("cost")):
        lines.append(f"Cost {a.money(num(r['cost']))}")
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{r.get('treatment', '')} - {r.get('animal', '')}", lines, color


def sum_health(a):
    overdue = soon = 0
    for r in a.db["health"]:
        d = days_until(r.get("next_due"))
        if d is not None and d < 0:
            overdue += 1
        elif d is not None and d <= 14:
            soon += 1
    lines = []
    if overdue:
        lines.append(f"{overdue} treatment(s) overdue")
    if soon:
        lines.append(f"{soon} due in the next 14 days")
    return lines


def view_breeding(a, r):
    due = breeding_due(r)
    lines = [f"{r.get('species', '')}  |  {r.get('status', '')}" + (f"  |  Sire: {r['sire']}" if r.get("sire") else ""),
             f"Mated {r.get('mated', '')}"]
    color = None
    if due:
        n = (due - today()).days
        lines.append(f"Expected {due.isoformat()} ({days_text(n)})")
        if r.get("status") not in ("Not pregnant", "Gave birth"):
            color = RED if n < 0 else AMBER if n <= 7 else None
    if r.get("notes"):
        lines.append(r["notes"])
    return r.get("animal", ""), lines, color


def view_production(a, r):
    lines = [r.get("date", "") + (f"  |  {r['source']}" if r.get("source") else "")]
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{fmt_num(r.get('qty'))}  {r.get('item', '')}", lines, None


def sum_production(a):
    totals = {}
    for r in a.db["production"]:
        if str(r.get("date", "")).startswith(a.month_key()):
            totals[r.get("item", "")] = totals.get(r.get("item", ""), 0) + num(r.get("qty"))
    if not totals:
        return []
    return ["This month:  " + "  |  ".join(f"{fmt_num(v)} {k}" for k, v in sorted(totals.items()))]


def view_fields(a, r):
    lines = [f"{fmt_num(r.get('area'))} ha  |  {r.get('status', '')}"]
    color = None
    if r.get("planted"):
        lines.append(f"Planted {r['planted']}")
    if r.get("harvest"):
        n = days_until(r["harvest"])
        lines.append(f"Harvest {r['harvest']} ({days_text(n)})")
        if r.get("status") != "Harvested" and n is not None:
            color = RED if n < 0 else AMBER if n <= 7 else None
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{r.get('name', '')} - {r.get('crop', '')}", lines, color


def sum_fields(a):
    if not a.db["fields"]:
        return []
    counts = {}
    for r in a.db["fields"]:
        counts[r.get("status", "")] = counts.get(r.get("status", ""), 0) + 1
    ha = sum(num(r.get("area")) for r in a.db["fields"])
    return [f"Total land: {fmt_num(ha)} ha  |  " + "  |  ".join(f"{k}: {v}" for k, v in sorted(counts.items()))]


def view_inventory(a, r):
    low = num(r.get("minimum")) > 0 and num(r.get("qty")) <= num(r.get("minimum"))
    lines = [r.get("category", "") + ("   LOW STOCK" if low else "")]
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{r.get('item', '')}: {fmt_num(r.get('qty'))} {r.get('unit', '')}", lines, (RED if low else None)


def sum_inventory(a):
    low = a.low_stock()
    return [f"{len(low)} item(s) low: " + ", ".join(r.get("item", "") for r in low)] if low else []


def view_tasks(a, r):
    done = bool(r.get("done"))
    lines = []
    color = MUTED if done else None
    if r.get("due"):
        n = days_until(r["due"])
        lines.append(f"Due {r['due']} ({days_text(n)})")
        if not done and n is not None:
            color = RED if n < 0 else AMBER if n <= 2 else None
    lines.append(f"Priority: {r.get('priority', 'Normal')}")
    if r.get("notes"):
        lines.append(r["notes"])
    return ("[Done]  " if done else "") + r.get("title", ""), lines, color


def sum_tasks(a):
    open_t = [r for r in a.db["tasks"] if not r.get("done")]
    over = sum(1 for r in open_t if (days_until(r.get("due")) or 0) < 0 and r.get("due"))
    return [f"{len(open_t)} open  |  {over} overdue"] if a.db["tasks"] else []


def view_workers(a, r):
    total = num(r.get("rate")) * num(r.get("days"))
    lines = [r.get("role", "")] if r.get("role") else []
    lines.append(f"{fmt_num(r.get('days'))} days x {a.money(num(r.get('rate')))}")
    if r.get("notes"):
        lines.append(r["notes"])
    return f"{r.get('name', '')}  -  {a.money(total)}", lines, None


def sum_workers(a):
    total = sum(num(r.get("rate")) * num(r.get("days")) for r in a.db["workers"])
    return [f"Wages owed this period: {a.money(total)}"] if a.db["workers"] else []


def view_contacts(a, r):
    lines = [r.get("role", "")]
    if r.get("phone"):
        lines.append(r["phone"])
    if r.get("notes"):
        lines.append(r["notes"])
    return r.get("name", ""), lines, None


def view_diary(a, r):
    lines = [r.get("date", "")]
    if r.get("note"):
        lines.append(r["note"])
    return r.get("title", ""), lines, None


MODULES = {
    "ledger": {
        "title": "Income & expenses", "noun": "transaction", "empty": "No money records yet. Tap ADD to log a sale or a cost.",
        "fields": [F("date", "Date", "date"), F("kind", "Type", "choice", choices=("Income", "Expense")),
                   F("category", "Category", "choice", choices=LEDGER_CATS),
                   F("description", "Description (optional)"), F("amount", "Amount", "num", req=True, pos=True)],
        "defaults": {"kind": "Expense", "category": "Feed"},
        "sort": lambda r: str(r.get("date", "")), "reverse": True, "view": view_ledger, "summary": sum_ledger},
    "livestock": {
        "title": "Livestock register", "noun": "animal group", "empty": "No livestock yet. Add a herd, flock or single animal.",
        "fields": [F("name", "Name / group (e.g. Broilers batch 3)", req=True), F("species", "Species", "choice", choices=SPECIES),
                   F("count", "Number of animals", "int", req=True), F("breed", "Breed / tag (optional)"),
                   F("acquired", "Date acquired (optional)", "date", opt=True), F("notes", "Notes", "note")],
        "defaults": {"species": "Cattle"},
        "sort": lambda r: (r.get("species", ""), r.get("name", "")), "view": view_livestock, "summary": sum_livestock,
        "actions": [("minus-circle-outline", "adjust", {"field": "count", "delta": -1}),
                    ("plus-circle-outline", "adjust", {"field": "count", "delta": 1})]},
    "health": {
        "title": "Animal health", "noun": "health record", "empty": "No health records yet. Log vaccinations, dosing and vet visits.",
        "fields": [F("animal", "Animal / group", req=True),
                   F("treatment", "Treatment", "choice", choices=("Vaccination", "Deworming", "Dipping / dosing", "Treatment", "Vet visit", "Other")),
                   F("date", "Date given", "date"), F("next_due", "Next due (optional)", "date", opt=True),
                   F("cost", "Cost (optional)", "num"), F("notes", "Notes", "note")],
        "defaults": {"treatment": "Vaccination"},
        "sort": lambda r: str(r.get("date", "")), "reverse": True, "view": view_health, "summary": sum_health,
        "actions": [("check-circle-outline", "clear_due", {})]},
    "breeding": {
        "title": "Breeding & hatching", "noun": "breeding record", "empty": "No breeding records yet. Log a mating or egg setting to get the due date.",
        "fields": [F("animal", "Female (name / tag / pen)", req=True), F("sire", "Male / sire (optional)"),
                   F("species", "Species", "choice", choices=tuple(GESTATION)), F("mated", "Mated / set on", "date"),
                   F("days", "Gestation days (only if you want to override)", "int"),
                   F("status", "Status", "choice", choices=("Mated", "Confirmed pregnant", "Not pregnant", "Gave birth")),
                   F("notes", "Notes", "note")],
        "defaults": {"species": "Cattle", "status": "Mated"},
        "sort": lambda r: str(r.get("mated", "")), "reverse": True, "view": view_breeding},
    "production": {
        "title": "Production log", "noun": "production entry", "empty": "No production yet. Log eggs, milk, honey or harvest weights.",
        "fields": [F("date", "Date", "date"),
                   F("item", "Product", "choice", choices=("Eggs (count)", "Milk (litres)", "Meat (kg)", "Wool (kg)", "Honey (kg)", "Crop harvest (kg)", "Fish (kg)", "Other")),
                   F("qty", "Quantity", "num", req=True, pos=True), F("source", "Source - field / herd (optional)"),
                   F("notes", "Notes", "note")],
        "defaults": {"item": "Eggs (count)"},
        "sort": lambda r: str(r.get("date", "")), "reverse": True, "view": view_production, "summary": sum_production},
    "fields": {
        "title": "Fields & crops", "noun": "field", "empty": "No fields yet. Add a field or plot with its crop and dates.",
        "fields": [F("name", "Field / plot name", req=True), F("crop", "Crop", req=True), F("area", "Area (hectares)", "num"),
                   F("planted", "Planting date (optional)", "date", opt=True),
                   F("harvest", "Expected harvest (optional)", "date", opt=True),
                   F("status", "Status", "choice", choices=("Planned", "Planted", "Growing", "Harvested")),
                   F("notes", "Notes", "note")],
        "defaults": {"status": "Planned"},
        "sort": lambda r: (r.get("status") == "Harvested", str(r.get("harvest") or "9999")), "view": view_fields,
        "summary": sum_fields},
    "inventory": {
        "title": "Stock & inventory", "noun": "stock item", "empty": "No stock yet. Add feed, seed, fertiliser, fuel and tools.",
        "fields": [F("item", "Item (e.g. Layer mash)", req=True),
                   F("category", "Category", "choice", choices=("Feed", "Seed", "Fertiliser", "Chemicals", "Fuel", "Medicine", "Tools & equipment", "Other")),
                   F("qty", "Quantity in stock", "num"), F("unit", "Unit", "choice", choices=("kg", "bags", "litres", "units", "boxes", "tons")),
                   F("minimum", "Warn me when stock falls to (optional)", "num"), F("notes", "Notes", "note")],
        "defaults": {"category": "Feed", "unit": "kg"},
        "sort": lambda r: (r.get("category", ""), r.get("item", "")), "view": view_inventory, "summary": sum_inventory,
        "actions": [("minus-circle-outline", "adjust", {"field": "qty", "delta": -1}),
                    ("plus-circle-outline", "adjust", {"field": "qty", "delta": 1})]},
    "tasks": {
        "title": "Tasks & reminders", "noun": "task", "empty": "No tasks yet. Add jobs like spraying, dipping or fixing a fence.",
        "fields": [F("title", "Task", req=True), F("due", "Due date (optional)", "date", opt=True),
                   F("priority", "Priority", "choice", choices=("Normal", "High", "Low")), F("notes", "Notes", "note")],
        "defaults": {"priority": "Normal"}, "extra": {"done": False},
        "sort": lambda r: (bool(r.get("done")), str(r.get("due") or "9999-99-99")), "view": view_tasks, "summary": sum_tasks,
        "actions": [("check-circle-outline", "toggle_done", {})]},
    "workers": {
        "title": "Workers & wages", "noun": "worker", "empty": "No workers yet. Add staff to track days worked and wages.",
        "fields": [F("name", "Name", req=True), F("role", "Role (optional)"), F("rate", "Pay per day", "num"),
                   F("days", "Days worked this period", "num"), F("notes", "Notes", "note")],
        "sort": lambda r: str(r.get("name", "")).lower(), "view": view_workers, "summary": sum_workers,
        "actions": [("cash-plus", "pay_worker", {})]},
    "contacts": {
        "title": "Contacts", "noun": "contact", "empty": "No contacts yet. Save buyers, suppliers and your vet.",
        "fields": [F("name", "Name", req=True),
                   F("role", "Who are they?", "choice", choices=("Buyer", "Supplier", "Vet", "Labour", "Neighbour", "Other")),
                   F("phone", "Phone number (optional)", "phone"), F("notes", "Notes", "note")],
        "defaults": {"role": "Buyer"},
        "sort": lambda r: str(r.get("name", "")).lower(), "view": view_contacts,
        "actions": [("phone", "call_contact", {})]},
    "diary": {
        "title": "Farm diary", "noun": "diary note", "empty": "No notes yet. Write down weather, observations and ideas.",
        "fields": [F("date", "Date", "date"), F("title", "Title", req=True), F("note", "Note", "note")],
        "sort": lambda r: str(r.get("date", "")), "reverse": True, "view": view_diary},
}


# ---------------------------------------------------------------- calculators
def tool_breakeven(a, v):
    if v["yield"] <= 0:
        raise ValueError("Enter an expected yield above zero.")
    be = v["cost"] / v["yield"]
    lines = [f"Break-even price: {a.money(be)} per unit"]
    if v["margin"]:
        if v["margin"] >= 100:
            raise ValueError("Profit margin must be below 100%.")
        lines.append(f"Price for a {fmt_num(v['margin'])}% margin: {a.money(be / (1 - v['margin'] / 100))} per unit")
    return lines


def tool_rate(a, v):
    total = v["area"] * v["rate"]
    lines = [f"Total needed: {total:,.1f} kg"]
    if v["bag"] > 0:
        lines.append(f"That is {math.ceil(total / v['bag'])} bag(s) of {fmt_num(v['bag'])} kg")
    if v["price"]:
        lines.append(f"Estimated cost: {a.money(total * v['price'])}")
    return lines


def tool_feed(a, v):
    total = v["animals"] * v["daily"] * v["days"]
    lines = [f"Total feed: {total:,.1f} kg"]
    if v["price"]:
        cost = total * v["price"]
        lines.append(f"Feed cost: {a.money(cost)}")
        if v["animals"]:
            lines.append(f"Cost per animal: {a.money(cost / v['animals'])}")
    return lines


def tool_loan(a, v):
    n = int(v["months"])
    if n <= 0:
        raise ValueError("Enter the number of months.")
    r = v["rate"] / 1200
    pay = v["amount"] / n if r == 0 else v["amount"] * r / (1 - (1 + r) ** -n)
    return [f"Monthly repayment: {a.money(pay)}", f"Total repaid: {a.money(pay * n)}",
            f"Total interest: {a.money(pay * n - v['amount'])}"]


def tool_population(a, v):
    if v["row"] <= 0 or v["plant"] <= 0:
        raise ValueError("Enter row and in-row spacing above zero.")
    per_ha = 10000 / (v["row"] * v["plant"])
    lines = [f"Plants per hectare: {per_ha:,.0f}"]
    if v["area"]:
        lines.append(f"Plants for {fmt_num(v['area'])} ha: {per_ha * v['area']:,.0f}")
    return lines


def tool_irrigation(a, v):
    times = v["times"] or 1
    litres = v["area"] * 10000 * v["depth"] * times
    return [f"Water needed: {litres:,.0f} litres", f"That is {litres / 1000:,.1f} cubic metres"]


def tool_fcr(a, v):
    if v["gain"] <= 0:
        raise ValueError("Enter the weight gained above zero.")
    lines = [f"Feed conversion ratio: {v['feed'] / v['gain']:.2f} kg feed per kg gain"]
    if v["price"]:
        lines.append(f"Feed cost per kg gained: {a.money(v['feed'] * v['price'] / v['gain'])}")
    return lines


CONVERSIONS = {"Hectares to acres": 2.47105, "Acres to hectares": 0.404686, "Kilograms to pounds": 2.20462,
               "Pounds to kilograms": 0.453592, "Litres to US gallons": 0.264172, "US gallons to litres": 3.78541,
               "Metres to feet": 3.28084, "Feet to metres": 0.3048, "Kilometres to miles": 0.621371,
               "Miles to kilometres": 1.60934, "Tonnes to kilograms": 1000, "Kilograms to tonnes": 0.001,
               "Square metres to hectares": 0.0001}


def tool_convert(a, v):
    return [f"{fmt_num(v['value'])}  ->  {v['value'] * CONVERSIONS[v['conv']]:,.4f}".rstrip("0").rstrip(".") + f"   ({v['conv']})"]


TOOLS = [
    {"name": "Break-even price", "desc": "The lowest price per unit that covers your costs, and the price for a target margin.",
     "fields": [F("cost", "Total costs", "num", req=True), F("yield", "Expected yield (units)", "num", req=True),
                F("margin", "Profit margin wanted % (optional)", "num")], "fn": tool_breakeven},
    {"name": "Seed / fertiliser / chemical rate", "desc": "Work out how much product a field needs from the rate per hectare.",
     "fields": [F("area", "Field area (hectares)", "num", req=True), F("rate", "Rate (kg per hectare)", "num", req=True),
                F("bag", "Bag size in kg (optional)", "num"), F("price", "Price per kg (optional)", "num")], "fn": tool_rate},
    {"name": "Livestock feed needs", "desc": "Total feed and feed cost for a group of animals over a period.",
     "fields": [F("animals", "Number of animals", "num", req=True), F("daily", "Feed per animal per day (kg)", "num", req=True),
                F("days", "Number of days", "num", req=True), F("price", "Feed price per kg (optional)", "num")], "fn": tool_feed},
    {"name": "Feed conversion (FCR)", "desc": "How many kilograms of feed it takes to put on one kilogram of weight.",
     "fields": [F("feed", "Total feed eaten (kg)", "num", req=True), F("gain", "Total weight gained (kg)", "num", req=True),
                F("price", "Feed price per kg (optional)", "num")], "fn": tool_fcr},
    {"name": "Loan repayment", "desc": "Monthly repayment and total interest on a farm loan.",
     "fields": [F("amount", "Loan amount", "num", req=True), F("rate", "Yearly interest rate %", "num", req=True),
                F("months", "Loan term (months)", "int", req=True)], "fn": tool_loan},
    {"name": "Plant population", "desc": "Plants per hectare from your row and in-row spacing.",
     "fields": [F("row", "Row spacing (metres)", "num", req=True), F("plant", "Spacing in the row (metres)", "num", req=True),
                F("area", "Field area in hectares (optional)", "num")], "fn": tool_population},
    {"name": "Irrigation water", "desc": "Litres needed to water a field to a given depth (1 mm on 1 ha = 10,000 litres).",
     "fields": [F("area", "Field area (hectares)", "num", req=True), F("depth", "Water depth per irrigation (mm)", "num", req=True),
                F("times", "Number of irrigations (optional)", "num")], "fn": tool_irrigation},
    {"name": "Unit converter", "desc": "Convert land, weight, volume and distance units.",
     "fields": [F("conv", "Convert", "choice", choices=tuple(CONVERSIONS)), F("value", "Value", "num", req=True)],
     "fn": tool_convert},
]

NAV = [
    ("section", "OVERVIEW"), ("dashboard", "Dashboard", "view-dashboard"),
    ("section", "MONEY"), ("costing", "Costing calculator", "calculator"), ("ledger", "Income & expenses", "cash"),
    ("section", "LIVESTOCK"), ("livestock", "Livestock register", "cow"), ("health", "Animal health", "medical-bag"),
    ("breeding", "Breeding & hatching", "heart"), ("production", "Production log", "egg"),
    ("section", "LAND & CROPS"), ("fields", "Fields & crops", "sprout"),
    ("section", "FARM OPERATIONS"), ("inventory", "Stock & inventory", "warehouse"),
    ("tasks", "Tasks & reminders", "clipboard-check"), ("workers", "Workers & wages", "account-hard-hat"),
    ("contacts", "Contacts", "account-group"), ("diary", "Farm diary", "notebook"),
    ("section", "TOOLS"), ("tools", "Farm calculators", "toolbox"), ("settings", "Settings & backup", "cog"),
]


class CostingApp(MDApp):
    title = "Farmer and Costing"
    categories = ("Crop", "Livestock")
    units = ("per kg", "per head", "per crate", "per litre", "per bag")
    presets = (("Chickens", "Livestock"), ("Cattle", "Livestock"), ("Goats", "Livestock"), ("Pigs", "Livestock"),
               ("Maize", "Crop"), ("Vegetables", "Crop"), ("Potatoes", "Crop"), ("Beans", "Crop"))

    # ------------------------------------------------------------ build / data
    def build(self):
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.accent_palette = "Amber"
        self.theme_cls.theme_style = "Light"
        Window.clearcolor = PAGE_BG
        Window.softinput_mode = "below_target"
        Window.bind(on_keyboard=self.on_key)

        self.records = []
        self.category = "Crop"
        self.unit = "per kg"
        self.smart_default_price = ""
        self.data_file = os.path.join(self.user_data_dir, "costings.json")
        self.db_file = os.path.join(self.user_data_dir, "farm_data.json")
        self.load_records()
        self.load_db()
        self.drawer_open = False
        self.restore_armed = False
        self.current = ("dashboard",)

        self.float = FloatLayout()
        main = MDBoxLayout(orientation="vertical")
        paint(main, PAGE_BG)

        header = MDBoxLayout(size_hint_y=None, height=dp(56), padding=(dp(4), 0, dp(12), 0), spacing=dp(4))
        paint(header, GREEN)
        self.menu_btn = MDIconButton(icon="menu", theme_icon_color="Custom", icon_color=WHITE,
                                     pos_hint={"center_y": 0.5})
        self.menu_btn.bind(on_release=lambda *_: self.menu_pressed())
        self.title_label = MDLabel(text="Dashboard", theme_text_color="Custom", text_color=WHITE, font_size=dp(20))
        self.title_label.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        header.add_widget(self.menu_btn)
        header.add_widget(self.title_label)
        main.add_widget(header)

        self.body = MDBoxLayout()
        main.add_widget(self.body)
        self.float.add_widget(main)
        self.show_page("dashboard")
        return self.float

    def load_db(self):
        db = {key: [] for key in MODULES}
        db["settings"] = {"farm_name": "", "currency": ""}
        try:
            with open(self.db_file, "r", encoding="utf-8") as data:
                saved = json.load(data)
            for key in MODULES:
                if isinstance(saved.get(key), list):
                    db[key] = saved[key]
            if isinstance(saved.get("settings"), dict):
                db["settings"].update(saved["settings"])
        except (OSError, ValueError, AttributeError):
            pass
        self.db = db

    def persist(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        tmp = self.db_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as data:
            json.dump(self.db, data, indent=1)
        os.replace(tmp, self.db_file)

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

    # ------------------------------------------------------------ shared helpers
    def money(self, value, decimals=2):
        cur = self.db["settings"].get("currency", "")
        sign = "-" if value < 0 else ""
        return f"{sign}{cur}{abs(value):,.{decimals}f}"

    def month_key(self):
        return today().strftime("%Y-%m")

    def ledger_totals(self, month=None):
        inc = exp = 0.0
        for r in self.db["ledger"]:
            if month and not str(r.get("date", "")).startswith(month):
                continue
            if r.get("kind") == "Income":
                inc += num(r.get("amount"))
            else:
                exp += num(r.get("amount"))
        return inc, exp

    def low_stock(self):
        return [r for r in self.db["inventory"] if num(r.get("minimum")) > 0 and num(r.get("qty")) <= num(r.get("minimum"))]

    def alerts(self):
        items = []
        for r in self.db["tasks"]:
            d = days_until(r.get("due"))
            if not r.get("done") and d is not None and d <= 14:
                items.append((d, f"Task - {r.get('title', '')}"))
        for r in self.db["health"]:
            d = days_until(r.get("next_due"))
            if d is not None and d <= 14:
                items.append((d, f"{r.get('treatment', 'Treatment')} - {r.get('animal', '')}"))
        for r in self.db["breeding"]:
            due = breeding_due(r)
            if due and r.get("status") not in ("Not pregnant", "Gave birth") and (due - today()).days <= 21:
                items.append(((due - today()).days, f"Birth / hatch expected - {r.get('animal', '')}"))
        for r in self.db["fields"]:
            d = days_until(r.get("harvest"))
            if r.get("status") != "Harvested" and d is not None and d <= 14:
                items.append((d, f"Harvest {r.get('crop', '')} - {r.get('name', '')}"))
        items.sort(key=lambda x: x[0])
        return items

    def toast(self, text):
        box = MDBoxLayout(size_hint=(0.9, None), height=dp(48), padding=(dp(14), 0), pos_hint={"center_x": 0.5, "y": 0.03})
        paint(box, (0.15, 0.17, 0.15, 0.95), dp(8))
        lbl = MDLabel(text=escape_markup(text), markup=True, theme_text_color="Custom", text_color=WHITE, font_size=dp(14))
        lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        box.add_widget(lbl)
        self.float.add_widget(box)
        Clock.schedule_once(lambda dt: self.float.remove_widget(box) if box.parent else None, 2.6)

    def label(self, text, size=15, color=None, bold=False, fixed=None):
        text = escape_markup(str(text))
        if bold:
            text = f"[b]{text}[/b]"
        kw = {"theme_text_color": "Custom", "text_color": color} if color else {"theme_text_color": "Primary"}
        lbl = MDLabel(text=text, markup=True, size_hint_y=None, height=dp(fixed or size + 8), font_size=dp(size), **kw)
        lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        if not fixed:
            lbl.bind(texture_size=lambda i, s: setattr(i, "height", max(s[1] + dp(4), dp(size + 6))))
        return lbl

    def button(self, text, callback, style="filled"):
        btn = MDButton(MDButtonText(text=text), style=style)
        btn.bind(on_release=lambda *_: callback())
        return btn

    def card(self, widgets, pad=12, spacing=4):
        c = MDCard(orientation="vertical", padding=dp(pad), radius=[dp(8)], size_hint_y=None, elevation=1)
        inner = MDBoxLayout(orientation="vertical", spacing=dp(spacing), size_hint_y=None)
        inner.bind(minimum_height=inner.setter("height"))
        inner.bind(height=lambda i, h: setattr(c, "height", h + dp(pad) * 2))
        for w in widgets:
            inner.add_widget(w)
        c.add_widget(inner)
        return c

    def new_page(self):
        scroll = ScrollView(do_scroll_x=False)
        content = MDBoxLayout(orientation="vertical", spacing=dp(10), padding=(dp(12), dp(10), dp(12), dp(28)),
                              size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        return scroll, content

    def delete_button(self, on_confirm):
        btn = MDIconButton(icon="delete-outline")
        state = {"armed": False}

        def reset(dt):
            state["armed"] = False
            btn.icon = "delete-outline"

        def pressed(*_):
            if not state["armed"]:
                state["armed"] = True
                btn.icon = "delete-forever"
                Clock.schedule_once(reset, 3)
                self.toast("Tap the bin again to delete")
            else:
                on_confirm()

        btn.bind(on_release=pressed)
        return btn

    def dropdown(self, caller, values, callback):
        menu = None

        def choose(value):
            callback(value)
            menu.dismiss()

        items = [{"text": value, "on_release": lambda selected=value: choose(selected)} for value in values]
        menu = MDDropdownMenu(caller=caller, items=items, max_height=dp(320))
        menu.open()

    # ------------------------------------------------------------ navigation
    def show_page(self, page, *args):
        self.close_drawer()
        self.current = (page,) + args
        if page == "dashboard":
            title, widget = self.page_dashboard()
        elif page == "costing":
            title, widget = self.page_costing()
        elif page == "tools":
            title, widget = self.page_tools()
        elif page == "tool":
            title, widget = self.page_tool(*args)
        elif page == "settings":
            title, widget = self.page_settings()
        elif page == "form":
            title, widget = self.page_form(*args)
        else:
            title, widget = self.page_module(page)
        self.body.clear_widgets()
        self.body.add_widget(widget)
        self.title_label.text = title
        self.menu_btn.icon = "arrow-left" if page in ("form", "tool") else "menu"

    def refresh_page(self):
        old = self.body.children[0] if self.body.children else None
        y = getattr(old, "scroll_y", 1)
        self.show_page(*self.current)
        Clock.schedule_once(lambda dt: setattr(self.body.children[0], "scroll_y", y) if self.body.children else None, 0.1)

    def go_back(self):
        page = self.current[0]
        if page == "form":
            self.show_page(self.current[1])
        elif page == "tool":
            self.show_page("tools")
        elif page != "dashboard":
            self.show_page("dashboard")

    def menu_pressed(self):
        if self.current[0] in ("form", "tool"):
            self.go_back()
        elif self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def on_key(self, window, key, *args):
        if key == 27:
            if self.drawer_open:
                self.close_drawer()
                return True
            if self.current[0] != "dashboard":
                self.go_back()
                return True
        return False

    def active_nav(self):
        page = self.current[0]
        return self.current[1] if page == "form" else "tools" if page == "tool" else page

    def open_drawer(self):
        if self.drawer_open:
            return
        self.drawer_open = True
        width = min(dp(290), Window.width * 0.82)
        self.scrim = Scrim(size_hint=(1, 1))
        self.scrim.bind(on_release=self.close_drawer)
        self.panel = Panel(orientation="vertical", size_hint=(None, 1), width=width)
        paint(self.panel, WHITE)
        head = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(110), padding=dp(16), spacing=dp(2))
        paint(head, GREEN)
        farm = self.db["settings"].get("farm_name") or "My Farm"
        head.add_widget(Widget())
        for text, size in ((farm, 20), ("Farm manager", 14)):
            lbl = MDLabel(text=escape_markup(text), markup=True, theme_text_color="Custom", text_color=WHITE,
                          font_size=dp(size), size_hint_y=None, height=dp(size + 10))
            lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
            head.add_widget(lbl)
        self.panel.add_widget(head)

        scroll = ScrollView(do_scroll_x=False)
        menu = MDBoxLayout(orientation="vertical", size_hint_y=None, padding=(dp(8), dp(6)), spacing=dp(2))
        menu.bind(minimum_height=menu.setter("height"))
        active = self.active_nav()
        for entry in NAV:
            if entry[0] == "section":
                section = MDLabel(text=entry[1], theme_text_color="Custom", text_color=MUTED, font_size=dp(12),
                                  size_hint_y=None, height=dp(30), padding=(dp(12), 0))
                section.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
                menu.add_widget(section)
                continue
            page, text, icon = entry
            row = Row(size_hint_y=None, height=dp(48), padding=(dp(12), 0), spacing=dp(16))
            if page == active:
                paint(row, (0.88, 0.95, 0.86, 1), dp(24))
            row.add_widget(MDIcon(icon=icon, theme_text_color="Custom", text_color=GREEN, font_size=dp(24),
                                  size_hint=(None, None), size=(dp(26), dp(26)), pos_hint={"center_y": 0.5}))
            name = MDLabel(text=escape_markup(text), markup=True, theme_text_color="Custom", text_color=DARK,
                           font_size=dp(15))
            name.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
            row.add_widget(name)
            row.bind(on_release=lambda *_, p=page: self.show_page(p))
            menu.add_widget(row)
        scroll.add_widget(menu)
        self.panel.add_widget(scroll)

        self.panel.x = -width
        self.float.add_widget(self.scrim)
        self.float.add_widget(self.panel)
        Animation(x=0, d=0.18, t="out_quad").start(self.panel)

    def close_drawer(self, *_):
        if not self.drawer_open:
            return
        self.drawer_open = False
        panel, scrim = self.panel, self.scrim
        anim = Animation(x=-panel.width, d=0.15)

        def done(*_):
            self.float.remove_widget(panel)
            self.float.remove_widget(scrim)

        anim.bind(on_complete=done)
        anim.start(panel)

    # ------------------------------------------------------------ dashboard
    def stat(self, title, value, color=None):
        box = MDCard(orientation="vertical", padding=dp(10), radius=[dp(8)], size_hint_y=None, height=dp(80), elevation=1)
        box.add_widget(self.label(title, 13, color=MUTED, fixed=20))
        box.add_widget(self.label(value, 20, color=color, bold=True, fixed=34))
        return box

    def page_dashboard(self):
        scroll, content = self.new_page()
        farm = self.db["settings"].get("farm_name") or "My Farm"
        content.add_widget(self.card([self.label(farm, 21, color=GREEN, bold=True),
                                      self.label(today().strftime("%A, %d %B %Y"), 14, color=MUTED)]))
        inc, exp = self.ledger_totals(self.month_key())
        head = sum(int(num(r.get("count"))) for r in self.db["livestock"])
        ha = sum(num(r.get("area")) for r in self.db["fields"])
        open_tasks = sum(1 for r in self.db["tasks"] if not r.get("done"))
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for title, value, color in (("Net this month", self.money(inc - exp, 0), OK if inc - exp >= 0 else RED),
                                    ("Income this month", self.money(inc, 0), None),
                                    ("Expenses this month", self.money(exp, 0), None),
                                    ("Livestock (head)", f"{head:,}", None),
                                    ("Land (hectares)", fmt_num(ha), None),
                                    ("Open tasks", str(open_tasks), None)):
            grid.add_widget(self.stat(title, value, color))
        content.add_widget(grid)

        quick = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        quick.add_widget(self.button("+ INCOME", lambda: self.show_page("form", "ledger", None, {"kind": "Income", "category": "Sales - crops"}), "outlined"))
        quick.add_widget(self.button("+ EXPENSE", lambda: self.show_page("form", "ledger", None, {"kind": "Expense", "category": "Feed"}), "outlined"))
        quick.add_widget(self.button("+ TASK", lambda: self.show_page("form", "tasks"), "outlined"))
        content.add_widget(quick)

        alerts = self.alerts()
        widgets = [self.label("Coming up", 17, bold=True)]
        if not alerts:
            widgets.append(self.label("Nothing due in the next 14 days.", 14, color=MUTED))
        for d, text in alerts[:12]:
            widgets.append(self.label(f"{days_text(d)}:  {text}", 14, color=RED if d < 0 else AMBER if d <= 3 else None))
        content.add_widget(self.card(widgets))

        low = self.low_stock()
        if low:
            widgets = [self.label("Low stock", 17, bold=True)]
            for r in low[:10]:
                widgets.append(self.label(f"{r.get('item', '')}: {fmt_num(r.get('qty'))} {r.get('unit', '')} left", 14, color=RED))
            content.add_widget(self.card(widgets))
        return "Dashboard", scroll

    # ------------------------------------------------------------ generic record pages
    def page_module(self, key):
        mod = MODULES[key]
        scroll, content = self.new_page()
        lines = mod["summary"](self) if mod.get("summary") else []
        if lines:
            content.add_widget(self.card([self.label(line, 14) for line in lines]))
        add = MDBoxLayout(size_hint_y=None, height=dp(48))
        add.add_widget(self.button(f"+ ADD {mod['noun'].upper()}", lambda: self.show_page("form", key)))
        content.add_widget(add)
        records = sorted(self.db[key], key=mod["sort"], reverse=mod.get("reverse", False))
        if not records:
            content.add_widget(self.label(mod["empty"], 15, color=MUTED))
        for rec in records:
            content.add_widget(self.record_card(key, rec))
        return mod["title"], scroll

    def record_card(self, key, rec):
        mod = MODULES[key]
        title, lines, color = mod["view"](self, rec)
        widgets = [self.label(title, 16, color=color, bold=True)]
        for line in lines:
            if line:
                widgets.append(self.label(line, 14, color=MUTED))
        bar = MDBoxLayout(size_hint_y=None, height=dp(48))
        bar.add_widget(Widget())
        for icon, handler, args in mod.get("actions", ()):
            btn = MDIconButton(icon=icon)
            btn.bind(on_release=lambda *_, h=handler, a=args: getattr(self, h)(key, rec, **a))
            bar.add_widget(btn)
        edit = MDIconButton(icon="pencil-outline")
        edit.bind(on_release=lambda *_: self.show_page("form", key, rec))
        bar.add_widget(edit)
        bar.add_widget(self.delete_button(lambda: self.delete_record(key, rec)))
        widgets.append(bar)
        return self.card(widgets)

    def delete_record(self, key, rec):
        self.db[key][:] = [r for r in self.db[key] if r is not rec]
        self.persist()
        self.refresh_page()

    def adjust(self, key, rec, field, delta):
        value = max(0, num(rec.get(field)) + delta)
        rec[field] = int(value) if field == "count" else value
        self.persist()
        self.refresh_page()

    def toggle_done(self, key, rec):
        rec["done"] = not rec.get("done")
        self.persist()
        self.refresh_page()

    def clear_due(self, key, rec):
        rec["next_due"] = ""
        self.persist()
        self.toast("Reminder cleared")
        self.refresh_page()

    def pay_worker(self, key, rec):
        total = num(rec.get("rate")) * num(rec.get("days"))
        if total <= 0:
            self.toast("Set a pay rate and days worked first")
            return
        self.db["ledger"].append({"date": today().isoformat(), "kind": "Expense", "category": "Labour",
                                  "description": f"Wages: {rec.get('name', '')}", "amount": total})
        rec["days"] = 0
        self.persist()
        self.toast("Wages added to Income & expenses; days reset to 0")
        self.refresh_page()

    def call_contact(self, key, rec):
        phone = "".join(ch for ch in str(rec.get("phone", "")) if ch.isdigit() or ch in "+*#")
        if not phone:
            self.toast("No phone number saved")
            return
        if platform == "android":
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")
                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                activity.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + phone)))
            except Exception:
                self.toast("Could not open the phone app")
        else:
            self.toast(f"Call {phone}")

    # ------------------------------------------------------------ forms
    def choice_button(self, f, current, values):
        txt = MDButtonText(text=f"{f['l']}: {current}")
        btn = MDButton(txt, style="outlined")

        def picked(value):
            values[f["k"]] = value
            txt.text = f"{f['l']}: {value}"

        btn.bind(on_release=lambda b: self.dropdown(b, f["choices"], picked))
        holder = MDBoxLayout(size_hint_y=None, height=dp(50))
        holder.add_widget(btn)
        return holder

    def build_field(self, f, raw, values, inputs):
        if f["t"] == "choice":
            current = raw if raw in f["choices"] else f["choices"][0]
            values[f["k"]] = current
            return self.choice_button(f, current, values)
        if f["t"] in ("num", "int") and raw not in ("", None):
            raw = fmt_num(raw)
        kw = {}
        children = [MDTextFieldHintText(text=f["l"])]
        if f["t"] == "date":
            children.append(MDTextFieldHelperText(text=f"Format: {today().isoformat()}", mode="on_focus"))
        if f["t"] == "num":
            kw.update(input_filter="float", input_type="number")
        elif f["t"] == "int":
            kw.update(input_filter="int", input_type="number")
        elif f["t"] == "phone":
            kw.update(input_type="number")
        note = f["t"] == "note"
        field = MDTextField(*children, mode="outlined", multiline=note, text=str(raw if raw is not None else ""),
                            size_hint_y=None, height=dp(110 if note else 56), **kw)
        inputs[f["k"]] = field
        holder = MDBoxLayout(size_hint_y=None, height=dp(122 if note else 68), padding=(0, dp(8), 0, 0))
        holder.add_widget(field)
        return holder

    def read_fields(self, fields, values, inputs):
        out = {}
        for f in fields:
            k, t = f["k"], f["t"]
            if t == "choice":
                out[k] = values[k]
                continue
            s = inputs[k].text.strip()
            if t in ("num", "int"):
                if s == "":
                    if f.get("req"):
                        return None, f"{f['l']} is required."
                    out[k] = 0
                    continue
                try:
                    v = float(s)
                except ValueError:
                    return None, f"{f['l']} must be a number."
                if v < 0 or (f.get("pos") and v <= 0):
                    return None, f"{f['l']} must be above zero." if f.get("pos") else f"{f['l']} cannot be negative."
                out[k] = int(round(v)) if t == "int" else v
            elif t == "date":
                if s == "":
                    if f.get("opt"):
                        out[k] = ""
                        continue
                    return None, f"{f['l']} is required (YYYY-MM-DD)."
                d = parse_date(s)
                if d is None:
                    return None, f"{f['l']}: use the format YYYY-MM-DD, e.g. {today().isoformat()}."
                out[k] = d.isoformat()
            else:
                if f.get("req") and not s:
                    return None, f"{f['l']} is required."
                out[k] = s
        return out, None

    def page_form(self, key, record=None, defaults=None):
        mod = MODULES[key]
        scroll, content = self.new_page()
        source = dict(mod.get("defaults", {}))
        source.update(defaults or {})
        if record:
            source = dict(record)
        values, inputs = {}, {}
        for f in mod["fields"]:
            raw = source.get(f["k"], "")
            if f["t"] == "date" and not record and raw == "" and not f.get("opt"):
                raw = today().isoformat()
            content.add_widget(self.build_field(f, raw, values, inputs))
        msg = self.label("", 14, color=RED)
        content.add_widget(msg)

        def save():
            out, err = self.read_fields(mod["fields"], values, inputs)
            if err:
                msg.text = err
                return
            if record is not None:
                record.update(out)
            else:
                new = dict(mod.get("extra", {}))
                new.update(out)
                self.db[key].append(new)
            self.persist()
            self.show_page(key)
            self.toast("Saved")

        bar = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        bar.add_widget(self.button("SAVE", save))
        bar.add_widget(self.button("CANCEL", lambda: self.show_page(key), "outlined"))
        content.add_widget(bar)
        return f"{'Edit' if record else 'New'} {mod['noun']}", scroll

    # ------------------------------------------------------------ calculators
    def page_tools(self):
        scroll, content = self.new_page()
        content.add_widget(self.label("Quick farm maths. Nothing here is saved.", 14, color=MUTED))
        for idx, tool in enumerate(TOOLS):
            row = Row(orientation="vertical", size_hint_y=None, height=dp(78), padding=dp(12), spacing=dp(2))
            paint(row, WHITE, dp(8))
            row.add_widget(self.label(tool["name"], 16, bold=True, fixed=26))
            row.add_widget(self.label(tool["desc"], 13, color=MUTED, fixed=36))
            row.bind(on_release=lambda *_, i=idx: self.show_page("tool", i))
            content.add_widget(row)
        return "Farm calculators", scroll

    def page_tool(self, idx):
        tool = TOOLS[idx]
        scroll, content = self.new_page()
        content.add_widget(self.label(tool["desc"], 14, color=MUTED))
        values, inputs = {}, {}
        for f in tool["fields"]:
            content.add_widget(self.build_field(f, "", values, inputs))
        result = self.label("Enter your numbers and tap CALCULATE.", 16, color=MUTED)

        def run():
            vals, err = self.read_fields(tool["fields"], values, inputs)
            if err:
                result.theme_text_color = "Custom"
                result.text_color = RED
                result.text = escape_markup(err)
                return
            try:
                lines = tool["fn"](self, vals)
            except ValueError as error:
                lines = [str(error)]
                result.theme_text_color = "Custom"
                result.text_color = RED
            except ZeroDivisionError:
                lines = ["Check your numbers: something is zero that should not be."]
                result.theme_text_color = "Custom"
                result.text_color = RED
            else:
                result.theme_text_color = "Primary"
            result.text = escape_markup("\n".join(lines))

        content.add_widget(self.button("CALCULATE", run))
        content.add_widget(self.card([result]))
        return tool["name"], scroll

    # ------------------------------------------------------------ settings, backup, reports
    def page_settings(self):
        scroll, content = self.new_page()
        fields = [F("farm_name", "Farm name"), F("currency", "Currency symbol (e.g. R, $, KSh)")]
        values, inputs = {}, {}
        for f in fields:
            content.add_widget(self.build_field(f, self.db["settings"].get(f["k"], ""), values, inputs))

        def save():
            out, err = self.read_fields(fields, values, inputs)
            if err:
                self.toast(err)
                return
            self.db["settings"].update(out)
            self.persist()
            self.toast("Settings saved")

        bar = MDBoxLayout(size_hint_y=None, height=dp(48))
        bar.add_widget(self.button("SAVE SETTINGS", save))
        content.add_widget(bar)

        content.add_widget(self.label("Backup & reports", 18, bold=True))
        content.add_widget(self.label("Everything is stored on this phone only. Copy a backup and paste it into a note or chat to keep it safe. Restoring replaces all current farm data.", 13, color=MUTED))
        for text, fn, style in (("COPY FULL BACKUP", self.copy_backup, "filled"),
                                ("RESTORE FROM CLIPBOARD", self.restore_backup, "outlined"),
                                ("COPY FARM SUMMARY", self.copy_summary, "outlined"),
                                ("COPY LEDGER AS CSV", self.copy_ledger_csv, "outlined")):
            line = MDBoxLayout(size_hint_y=None, height=dp(48))
            line.add_widget(self.button(text, fn, style))
            content.add_widget(line)
        return "Settings & backup", scroll

    def copy_backup(self):
        payload = {"app": "farmer-and-costing", "version": 2, "data": self.db, "costings": self.records}
        Clipboard.copy(json.dumps(payload))
        self.toast("Backup copied. Paste it somewhere safe.")

    def restore_backup(self):
        if not self.restore_armed:
            self.restore_armed = True
            Clock.schedule_once(lambda dt: setattr(self, "restore_armed", False), 6)
            self.toast("Tap again within 6 seconds to replace ALL data with the backup on the clipboard")
            return
        self.restore_armed = False
        try:
            payload = json.loads(Clipboard.paste())
            if payload.get("app") != "farmer-and-costing" or not isinstance(payload.get("data"), dict):
                raise ValueError
        except (ValueError, AttributeError, TypeError):
            self.toast("The clipboard does not hold a Farmer and Costing backup")
            return
        for key in MODULES:
            if isinstance(payload["data"].get(key), list):
                self.db[key] = payload["data"][key]
        if isinstance(payload["data"].get("settings"), dict):
            self.db["settings"].update(payload["data"]["settings"])
        if isinstance(payload.get("costings"), list):
            self.records = payload["costings"]
            self.persist_records()
        self.persist()
        self.toast("Backup restored")
        self.show_page("dashboard")

    def copy_ledger_csv(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Date", "Type", "Category", "Description", "Amount"])
        for r in sorted(self.db["ledger"], key=lambda r: str(r.get("date", ""))):
            writer.writerow([r.get("date", ""), r.get("kind", ""), r.get("category", ""), r.get("description", ""),
                             f"{num(r.get('amount')):.2f}"])
        Clipboard.copy(buffer.getvalue())
        self.toast("Ledger copied as CSV. Paste it into a spreadsheet or message.")

    def copy_summary(self):
        s = self.db["settings"]
        mi, me = self.ledger_totals(self.month_key())
        ai, ae = self.ledger_totals()
        lines = [f"{s.get('farm_name') or 'My Farm'} - farm summary ({today().isoformat()})", "",
                 f"Money this month: income {self.money(mi)}, expenses {self.money(me)}, net {self.money(mi - me)}",
                 f"Money all time: income {self.money(ai)}, expenses {self.money(ae)}, net {self.money(ai - ae)}", ""]
        for title, builder in (("Livestock", sum_livestock), ("Land", sum_fields), ("Production", sum_production),
                               ("Stock", sum_inventory), ("Tasks", sum_tasks), ("Workers", sum_workers),
                               ("Health", sum_health)):
            for line in builder(self):
                lines.append(f"{title}: {line}")
        alerts = self.alerts()
        if alerts:
            lines += ["", "Coming up:"] + [f"- {days_text(d)}: {text}" for d, text in alerts]
        Clipboard.copy("\n".join(lines))
        self.toast("Summary copied. Paste it into a message or note.")

    # ------------------------------------------------------------ costing calculator (original tool)
    def page_costing(self):
        scroll, content = self.new_page()
        self.category = "Crop"
        self.unit = "per kg"
        self.smart_default_price = ""

        details_card = MDCard(orientation="vertical", padding=dp(12), spacing=dp(8), radius=[dp(8)],
                              size_hint_y=None, height=dp(450), elevation=1)
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
        details_card.add_widget(selectors)
        details_card.add_widget(self.preset_button)

        form = GridLayout(cols=2, spacing=dp(10), padding=(dp(4), dp(4)), size_hint_y=None, height=dp(330))
        self.inputs = {}
        fields = [("Crop/stock name", "name", "e.g. Chickens"),
                  ("Seed/feed cost", "seed_cost", "0.00"),
                  ("Labor cost", "labor_cost", "0.00"),
                  ("Other costs", "other_cost", "0.00"),
                  ("Target yield", "yield", "0.00"),
                  ("Expected price", "price", "editable; remembers the latest saved price")]
        for label_text, key, hint in fields:
            kw = {} if key == "name" else {"input_filter": "float", "input_type": "number"}
            field = MDTextField(MDTextFieldHintText(text=label_text),
                                MDTextFieldHelperText(text=hint, mode="on_focus"),
                                mode="outlined", multiline=False, **kw)
            self.inputs[key] = field
            form.add_widget(field)
        self.inputs["name"].bind(focus=self.name_focus_changed)
        details_card.add_widget(form)
        content.add_widget(details_card)

        actions = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        actions.add_widget(self.button("CALCULATE", self.calculate))
        actions.add_widget(self.button("SAVE ENTRY", self.save_entry))
        content.add_widget(actions)

        self.summary_profit = self.label("Estimated profit/loss: --", 21, color=OK, bold=True)
        self.result = self.label("Enter values to see the estimate.", 15, color=MUTED)
        content.add_widget(self.card([self.summary_profit, self.result]))

        content.add_widget(self.label("Saved entries", 19, bold=True))
        self.entry_list = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.entry_list.bind(minimum_height=self.entry_list.setter("height"))
        content.add_widget(self.entry_list)
        self.refresh_entries()
        return "Costing calculator", scroll

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
            self.result.text = f"Latest saved price loaded for {escape_markup(previous['name'])}. You can edit it for today's market."

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
        qty = self.number("yield")
        breakeven = f"\nBreak-even price: {expenses / qty:,.2f} {self.unit}" if qty else ""
        self.result.text = (f"Total cost: {expenses:,.2f}\nExpected revenue: {revenue:,.2f}\n"
                            f"Profit margin: {margin:.1f}%{breakeven}")
        self.summary_profit.text = f"[b]Estimated profit/loss: {profit:,.2f}[/b]"
        self.summary_profit.text_color = OK if profit >= 0 else RED

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
        self.result.text = f"Saved {escape_markup(name)}. Latest price will be suggested next time."

    def delete_costing(self, record):
        self.records[:] = [r for r in self.records if r is not record]
        self.persist_records()
        self.refresh_entries()

    def refresh_entries(self):
        self.entry_list.clear_widgets()
        if not self.records:
            self.entry_list.add_widget(self.label("No saved entries yet.", 14, color=MUTED))
        for record in self.records:
            profit = record.get("profit", 0)
            bar = MDBoxLayout(size_hint_y=None, height=dp(44))
            bar.add_widget(Widget())
            bar.add_widget(self.delete_button(lambda r=record: self.delete_costing(r)))
            self.entry_list.add_widget(self.card([
                self.label(f"{record.get('name', '')}  |  {record.get('category', 'Crop')}  |  {record.get('unit', 'per kg')}", 16, bold=True),
                self.label(f"Cost {record.get('expenses', 0):,.2f}  |  Revenue {record.get('revenue', 0):,.2f}", 14, color=MUTED),
                self.label(f"Profit {profit:,.2f}", 14, color=OK if profit >= 0 else RED, bold=True),
                bar]))


if __name__ == "__main__":
    CostingApp().run()
