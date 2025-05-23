#!/bin/python3.12


import argparse
import datetime
import requests
import difflib
import pickle
import json
import sys
import re
import os


restaurants = [
  "PIRACICABA",                               # 01
  "CENTRAL SAO CARLOS SC",                    # 02
  "CAMPUS II SAO CARLOS SC",                  # 03
  "CRHEA SAO CARLOS SC",                      # 04
  "PIRASSUNUNGA",                             # 05
  "CENTRAL",                                  # 06
  "PUSP-C SAO PAULO SP",                      # 07
  "FISICA",                                   # 08
  "QUIMICA",                                  # 09
  "ADMINISTRACAO SAO PAULO SP",               # 10
  "FACULDADE SAUDE PUBLICA",                  # 11
  "ESCOLA ENFERMAGEM",                        # 12
  "EACH SAO PAULO SP",                        # 13
  "FACULDADE DIREITO",                        # 14
  "DPS CUASO SAO PAULO SP",                   # 15
  "DPS EACH SAO PAULO SP",                    # 16
  "EEL AREA I",                               # 17
  "MEDICINA SAO PAULO SP",                    # 18
  "RIBEIRAO PRETO",                           # 19
  "BAURU",                                    # 20
  "PREFEITURA FERNANDO COSTA PIRASSUNUNGA",   # 21
  "WEB",                                      # 22
  "EEL AREA II",                              # 23
  "REGISTRO ESTORNO",                         # 24
]


verbose_mode: bool = False

def eprint(*args, **kwargs):
  if verbose_mode:
    print(file=sys.stderr, *args, **kwargs)


HOME = os.path.expanduser("~")

def open_cache(key:str, mode: str):
  os.makedirs(f"{HOME}/.cache/bandeco", exist_ok=True)
  return open(f"{HOME}/.cache/bandeco/{key}", mode)


def sanitise_entry(entry: tuple[str, str, str, str]):
  menu, date, meal, calories = entry
  
  # Sanitise the menu string
  menu = (
    menu
    .replace("\\/", "/")
    .encode().decode("unicode_escape")
    .replace("<br>", "\n")
    .replace("\\", "")
  )

  # Sanitise the date string
  date = date.replace("\\", "")

  # Map the meal to its name
  meal = {
    "A": "lunch",
    "J": "dinner",
  }[meal]

  # Convert the calories to an integer
  calories = int(calories)

  return {
    "menu"     : menu,
    "date"     : date,
    "meal"     : meal,
    "calories" : calories,
  }


def entry_to_key_value(entries: tuple[str, str, str, str]):
  value = sanitise_entry(entries)
  key = f"{value['date']}-{value['meal']}"
  
  # Key-value pairs for the dict constructor
  return (key, { 'menu': value['menu'], 'calories': value['calories'] })


def fetch_entries_http(restaurant: int) -> dict[str]:
  data = (
    "callCount=1\n"
    "windowName=\n"
    "nextReverseAjaxIndex=0\n"
    "c0-scriptName=CardapioControleDWR\n"
    "c0-methodName=obterCardapioRestUSP\n"
    "c0-id=0\n"
    "c0-param0=string:" + str(restaurant) + "\n"
    "batchId=1\n"
    "instanceId=0\n"
    "page=\n"
    "scriptSessionId=1/2-34\n"
  )

  url = (
    "https://uspdigital.usp.br/rucard/dwr/call/plaincall/"
    "CardapioControleDWR.obterCardapioRestUSP.dwr"
  )

  regex = (
    r'cdpdia:"(.+?)",.*?'
    r'dtarfi:"(.+?)",.*?'
    r'tiprfi:"(\w)",.*?'
    r'vlrclorfi:(\d+)'
  )

  eprint("Requesting MENU over HTTP...")
  response = requests.post(url, data)

  entries = re.findall(regex, response.text)
  eprint(f"- Request parsed ({len(entries)} entries)")

  return dict(entry_to_key_value(entry) for entry in entries)


def fetch_entries_cached(key: str) -> dict[str] | None:
  try:
    eprint(f'Attempting to open cache "{key}"...')
    with open_cache(key, "rb") as cache:
      eprint("- Cache hit")
      return pickle.load(cache)
  except Exception as ex:
    eprint("- Cache miss:", ex)
    return None


def store_entries_cache(key: str, entries: dict[str]):
  with open_cache(key, "wb") as cache:
    pickle.dump(entries, cache)


def get_week(date: datetime.date) -> str:
  week = date.strftime("%Yw%W")
  if week.endswith("w00"):
    week = datetime.datetime(date.year - 1, 12, 31).strftime("%Yw%W")
  return week


def cache_key(date: datetime.date, restaurant: int):
  return f"{get_week(date)}r{restaurant:02}"


def is_current_week(date: datetime.date):
  today = datetime.date.today()
  return get_week(date) == get_week(today)


def get_date(day: str):
  today = datetime.date.today()

  if day == "today":
    return today
  elif day == "tomorrow":
    return today + datetime.timedelta(days=1)
  elif day == "yesterday":
    return today - datetime.timedelta(days=1)

  def parse_with_format(day: str, format: str, defaults: str):
    try:
      full_str = f"{day}|{today.strftime(defaults)}"
      parsed = datetime.datetime.strptime(full_str, f"{format}|{defaults}")
      return parsed.date()
    except ValueError as err:
      eprint("Parse attempt:", err)
      return None
  
  formats: list[tuple[str, str]] = [
    # User input , Today
    ( "%a"       , "%W %Y" ),
    ( "%A"       , "%W %Y" ),
    ( "%d/%m"    , "%Y"    ),
    ( "%d/%m/%y" , ""      ),
    ( "%d/%m/%Y" , ""      ),
  ]

  for format, defaults in formats:
    parsed = parse_with_format(day, format, defaults)
    if parsed is not None:
      return parsed

  print(
    "Invalid date format. Available formats are:\n"
    "\n"
    "- Today         (For today)\n"
    "- Tomorrow      (For tomorrow)\n"
    "- Yesterday     (For yesterday)\n"
    "- Fri           (For this week's friday)\n"
    "- Friday\n"
    "- 01/01         (For the first of January of this year)\n"
    "- 01/01/01      (For the first of January of 2001)\n"
    "- 01/01/1901    (For the first of January of 1901)\n"
    "\n"
    "The formats are case insensitive and dependent on your locale.\n"
  )
  raise ValueError("Unable to parse input date")


def get_restaurant_code(search: str):
  eprint(f"Search term = {search.upper()}")
  
  def compare(entry: tuple[int, str]):
    ratio = difflib.SequenceMatcher(None, search.upper(), entry[1]).ratio()
    eprint(f"{entry[1]:40} {ratio}")
    return ratio

  return max(enumerate(restaurants), key=compare)[0] + 1


def parse_args():
  global verbose_mode

  parser = argparse.ArgumentParser(
    description="Fetches USP's university restaurant menu for the day"
  )

  parser.add_argument(
    '-d', '--day', type=str,
    default='today',
    help="Day to fetch the menu for. Can be a day of the week or a date."
  )
  parser.add_argument(
    '-m', '--meal',
    type=lambda s: s.lower(),
    choices=['l', 'lunch', 'd', 'dinner', 'a', 'all'],
    default='all',
    help="Meal of the day to fetch the menu for."
  )
  parser.add_argument(
    '-r', '--restaurant',
    type=str, default='each',
    help="Name of the restaurant to fetch the menu for."
  )
  parser.add_argument(
    '-w', '--week',
    action='store_true',
    help="Display the entire week's menu."
  )
  parser.add_argument(
    '-v', '--verbose',
    action='store_true',
    help="Print verbose output."
  )
  parser.add_argument(
    '-j', '--json',
    action='store_true',
    help="Output in JSON."
  )

  parsed = parser.parse_args()

  verbose_mode = parsed.verbose
  eprint("=== Parsing day...")
  day: datetime.date = get_date(parsed.day)
  meal: str = parsed.meal[0]
  week: bool = parsed.week
  json: bool = parsed.json
  eprint("=== Parsing restaurant...")
  restaurant = get_restaurant_code(parsed.restaurant)

  eprint("ARGS:", (day, meal, restaurant))

  return (json, restaurant, day, meal, week)


def display_day_menu(entries: dict[str], day: datetime.date, meal: str):
  date = day.strftime("%d/%m/%Y")
  weekday = day.strftime("%A")
  print(f"\033[1;93m## {weekday} ({date})\033[m")
  if meal == "l" or meal == "a":
    print("\033[1;93m### Lunch:\033[m")
    print(entries[f"{date}-lunch"]['menu'])
    calories = entries[f"{date}-lunch"]['calories']
    print(f"\n\033[1mCalories: {calories} Kcal\033[m")
  if meal == "d" or meal == "a":
    print("\033[1;93m### Dinner:\033[m")
    print(entries[f"{date}-dinner"]['menu'])
    calories = entries[f"{date}-dinner"]['calories']
    print(f"\n\033[1mCalories: {calories} Kcal\033[m")


def display_week_menu(entries: dict[str], day: datetime.date, meal: str):
  week = day.strftime("%W-%Y")
  for weekday in range(1, 6):
    date = datetime.datetime.strptime(f"{weekday}-{week}", "%w-%W-%Y").date()
    display_day_menu(entries, date, meal)


def day_menu_object(entries: dict[str], day: datetime.date, meal: str):
  date = day.strftime("%d/%m/%Y")
  weekday = day.strftime("%A").lower()

  data = {
    'date': date,
    'weekday': weekday,
  }

  if meal == "l" or meal == "a":
    data['lunch'] = entries[f"{date}-lunch"]
  if meal == "d" or meal == "a":
    data['dinner'] = entries[f"{date}-dinner"]

  return data


def week_menu_object(entries: dict[str], day: datetime.date, meal: str):
  week = day.strftime("%W-%Y")

  return [
    day_menu_object(entries, date, meal)
    for date in (
      datetime.datetime.strptime(f"{weekday}-{week}", "%w-%W-%Y").date()
      for weekday in range(1, 6)
    )
  ]


def display_pretty(entries: dict[str], options: tuple):
  restaurant, day, meal, week = options

  print(f"\033[1;93m# {restaurants[restaurant - 1]}\033[m")

  if week:
    display_week_menu(entries, day, meal)
  else:
    display_day_menu(entries, day, meal)


def display_json(entries: dict[str], options: tuple):
  restaurant, day, meal, week = options

  data = {
    'restaurant': restaurants[restaurant - 1],
    'data': (
      week_menu_object(entries, day, meal)
      if week else
      day_menu_object(entries, day, meal)
    )
  }

  print(json.dumps(data, indent=2))


def main():
  json, restaurant, day, *options = parse_args()

  key = cache_key(day, restaurant)
  entries = fetch_entries_cached(key)
  
  if entries is None:
    if not is_current_week(day):
      print("Unable to fetch menu for the requested date.")
      return 1
  
    entries = fetch_entries_http(restaurant)
  
    if not entries:
      print("Failed to fetch menu for the requested restaurant.")
      return 1

    store_entries_cache(key, entries)
  
  if json:
    display_json(entries, (restaurant, day, *options))
  else:
    display_pretty(entries, (restaurant, day, *options))

  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception as ex:
    print("Error:", ex)
    sys.exit(1)


