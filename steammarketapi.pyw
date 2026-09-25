import requests
import sys
import time
import csv
import os
import math
from datetime import datetime, timedelta

try:
    from tkinter import Tk, messagebox
except ImportError:
    Tk = None
    messagebox = None

CSV_FILE = "steammarketprices.csv"
FALLBACK_NAMES = {
    "730": "Counter-Strike 2",
}

NO_ENTER = "--no-enter-to-exit" in sys.argv
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9",
}
_last_request_time = 0


def _throttled_get(url, **kwargs):
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < 3:
        time.sleep(3 - elapsed)
    _last_request_time = time.time()
    return requests.get(url, **kwargs)

DEFAULT_GAMES = {
    "cs2": {
        "app_id": 730,
        "items": [
            {"name": "Nova | Candy Apple (Minimal Wear)", "buy_price": 0}
        ],
    },
}





def get_steam_price(item_name, app_id=730, currency=2, max_retries=3, retry_delay=3):
    url = "https://steamcommunity.com/market/priceoverview/"
    params = {
        "appid": app_id,
        "currency": currency,
        "market_hash_name": item_name
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = _throttled_get(url, params=params, headers=HEADERS, timeout=10)
            if response.status_code == 429:
                last_error = f"HTTP 429: Rate limited (attempt {attempt}/{max_retries})"
                time.sleep(retry_delay * attempt)
                continue
            if response.status_code in (400, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}: Server error (attempt {attempt}/{max_retries})"
                time.sleep(retry_delay)
                continue
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                last_error = f"API returned success=false (attempt {attempt}/{max_retries})"
                time.sleep(retry_delay)
                continue
            median_price = data.get("median_price")
            if median_price:
                return median_price, None
            lowest_price = data.get("lowest_price")
            if lowest_price:
                return lowest_price, None
            last_error = f"No price data in response (attempt {attempt}/{max_retries}): {data}"
            time.sleep(retry_delay)
        except requests.ConnectionError:
            last_error = f"Connection failed (attempt {attempt}/{max_retries})"
            time.sleep(retry_delay)
        except requests.Timeout:
            last_error = f"Request timed out (attempt {attempt}/{max_retries})"
            time.sleep(retry_delay)
        except requests.RequestException as e:
            last_error = f"Request error: {e} (attempt {attempt}/{max_retries})"
            time.sleep(retry_delay)
        except ValueError as e:
            last_error = f"Invalid JSON response: {e}"
            break
    return None, last_error or "Unknown error"


def save_to_csv(game, item_name, price):
    exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "game", "item_name", "price"])
        w.writerow([datetime.now().isoformat(), game, item_name, price])


def get_app_name(app_id):
    try:
        r = _throttled_get(f"https://store.steampowered.com/api/appdetails?appids={app_id}", headers=HEADERS, timeout=10)
        data = r.json()
        if data.get(str(app_id), {}).get("success"):
            return data[str(app_id)]["data"]["name"]
    except Exception:
        pass
    return None


def item_exists(item_name, app_id):
    try:
        r = _throttled_get("https://steamcommunity.com/market/priceoverview/", params={"appid": app_id, "market_hash_name": item_name, "currency": 2}, headers=HEADERS, timeout=10)
        return r.json().get("success") is True
    except Exception:
        return False


def _to_float(price_str):
    return float(price_str.replace("$", "").replace("£", "")) if price_str else 0


def _seller_receives(price):
    valve = max(math.floor(round(price / 1.15 * 0.05, 3) * 100) / 100, 0.01)
    game = max(math.floor(round(price / 1.15 * 0.1, 3) * 100) / 100, 0.01)
    return round(price - valve - game, 2)


def _break_even(buy_price):
    est = buy_price * 1.15
    while _seller_receives(est) < buy_price:
        est = round(est + 0.01, 2)
    while _seller_receives(round(est - 0.01, 2)) >= buy_price:
        est = round(est - 0.01, 2)
    return est


REQUIRED_HEADERS = ["timestamp", "game", "item_name", "price"]


def _norm(items):
    return [{"name": i, "buy_price": 0} if isinstance(i, str) else i for i in items]


def _fmt_games():
    lines = ["DEFAULT_GAMES = {\n"]
    for key, cfg in DEFAULT_GAMES.items():
        items_lines = ",\n".join(
            f'            {{"name": "{i["name"]}", "buy_price": {i.get("buy_price", 0)}}}'
            for i in cfg["items"]
        )
        lines.append(f'    "{key}": {{\n')
        lines.append(f'        "app_id": {cfg["app_id"]},\n')
        lines.append(f'        "items": [\n{items_lines}\n        ],\n')
        lines.append("    },\n")
    lines.append("}\n")
    return "".join(lines)


def _fmt_fallbacks():
    lines = ["FALLBACK_NAMES = {\n"]
    for aid, name in FALLBACK_NAMES.items():
        lines.append(f'    "{aid}": "{name}",\n')
    lines.append("}\n")
    return "".join(lines)


def _clone_script():
    base_games = {
        "cs2": {
            "app_id": 730,
            "items": [{"name": "Nova | Candy Apple (Minimal Wear)", "buy_price": 0.19}],
        },
    }
    base_fallbacks = {"730": "Counter-Strike 2"}

    # Generate formatted strings for the base configuration
    orig_games, orig_fallbacks = DEFAULT_GAMES, FALLBACK_NAMES
    
    # Use local formatting functions to avoid dependency on global state
    def local_fmt_games(games):
        lines = ["DEFAULT_GAMES = {\n"]
        for key, cfg in games.items():
            items_lines = ",\n".join(
                f'            {{"name": "{i["name"]}", "buy_price": {i.get("buy_price", 0)}}}'
                for i in cfg["items"]
            )
            lines.append(f'    "{key}": {{\n')
            lines.append(f'        "app_id": {cfg["app_id"]},\n')
            lines.append(f'        "items": [\n{items_lines}\n        ],\n')
            lines.append("    },\n")
        lines.append("}\n")
        return "".join(lines)

    def local_fmt_fallbacks(fallbacks):
        lines = ["FALLBACK_NAMES = {\n"]
        for aid, name in fallbacks.items():
            lines.append(f'    "{aid}": "{name}",\n')
        lines.append("}\n")
        return "".join(lines)

    base_games_str = local_fmt_games(base_games)
    base_fallbacks_str = local_fmt_fallbacks(base_fallbacks)

    with open(__file__, "r", encoding="utf-8") as f:
        content = f.read()

    # Identify blocks for replacement
    start = content.index("DEFAULT_GAMES = {")
    depth = 0
    end = start
    for i in range(start, len(content)):
        if content[i] == "{": depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    fallback_start = content.index("FALLBACK_NAMES = {")
    fallback_depth = 0
    fallback_end = fallback_start
    for i in range(fallback_start, len(content)):
        if content[i] == "{": fallback_depth += 1
        elif content[i] == "}":
            fallback_depth -= 1
            if fallback_depth == 0:
                fallback_end = i + 1
                break

    replacements = [
        (start, end, base_games_str),
        (fallback_start, fallback_end, base_fallbacks_str)
    ]
    replacements.sort(key=lambda x: x[0], reverse=True)

    for r_start, r_end, r_text in replacements:
        content = content[:r_start] + r_text + content[r_end:]

    with open("steammarketapi_clone.pyw", "w", encoding="utf-8") as f:
        f.write(content)
    print("Cloned base script to steammarketapi_clone.pyw")


def validate_csv():
    if not os.path.isfile(CSV_FILE):
        return

    name_map = {}
    for cfg in DEFAULT_GAMES.values():
        name_map[str(cfg["app_id"])] = get_app_name(cfg["app_id"]) or str(cfg["app_id"])
    
    # Ensure consistency by mapping common app IDs to their proper names
    for aid, name in FALLBACK_NAMES.items():
        if aid not in name_map or name_map[aid] == aid:
            name_map[aid] = name

    name_map["cs2"] = name_map.get("730", "Counter-Strike 2")
    name_map["tbh"] = name_map.get("3678970", "TBH: Task Bar Hero")
    old = os.path.splitext(CSV_FILE)[0] + "_old.csv"

    with open(CSV_FILE, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = [row for row in reader if any(v.strip() for v in row)]

    if header != REQUIRED_HEADERS:
        os.replace(CSV_FILE, old)
        print(f"Migrated old CSV header to {old}")
        return

    changed = False
    for row in rows:
        if len(row) == 4 and row[1] in name_map:
            new_name = name_map[row[1]]
            if row[1] != new_name:
                row[1] = new_name
                changed = True
        elif len(row) == 4 and row[1].isdigit():
            # Resolve cases where the game name is stored as a numeric app ID
            aid = row[1]
            if aid in name_map:
                new_name = name_map[aid]
                if row[1] != new_name:
                    row[1] = new_name
                    changed = True

    if changed:
        os.replace(CSV_FILE, old)
        with open(CSV_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(REQUIRED_HEADERS)
            w.writerows(rows)
        print(f"Normalized game names, old data in {old}")


def wait():
    if not NO_ENTER:
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass


def _show_dialog(title, message, icon="warning"):
    if Tk is None or messagebox is None:
        print(f"\n{title}: {message}")
        return
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    if icon == "error":
        messagebox.showerror(title, message, parent=root)
    elif icon == "info":
        messagebox.showinfo(title, message, parent=root)
    else:
        messagebox.showwarning(title, message, parent=root)
    root.destroy()


def _build_graph():
    if not os.path.isfile(CSV_FILE):
        print("No data to graph.")
        return None

    rows = []
    with open(CSV_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("No data to graph.")
        return None

    from collections import defaultdict

    data = defaultdict(lambda: {"times": [], "prices": []})
    for r in rows:
        key = f"[{r['game']}] {r['item_name']}"
        try:
            t = datetime.fromisoformat(r["timestamp"])
            p = _to_float(r["price"])
            data[key]["times"].append(t)
            data[key]["prices"].append(p)
        except (ValueError, KeyError):
            continue

    if not data:
        print("No valid data to graph.")
        return None

    buy_price_map = {}
    for cfg in DEFAULT_GAMES.values():
        for item in cfg["items"]:
            name = item["name"] if isinstance(item, dict) else item
            bp = item.get("buy_price", 0) if isinstance(item, dict) else 0
            if bp:
                buy_price_map[name] = _break_even(bp)

    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fig, ax = plt.subplots(figsize=(14, 5))
    for label, pts in data.items():
        if pts["times"]:
            line, = ax.plot(pts["times"], pts["prices"], marker="o", markersize=3, label=label)
            item_name = label.split("] ", 1)[-1]
            if item_name in buy_price_map:
                be = buy_price_map[item_name]
                ax.axhline(y=be, color=line.get_color(), alpha=0.3, linewidth=1, linestyle="--")
                ax.annotate(f"{int(round(be * 100))}p", xy=(1, be), xycoords=ax.get_yaxis_transform(),
                            ha="left", va="center", fontsize=7, color=line.get_color(), alpha=0.6,
                            xytext=(4, 0), textcoords="offset points")

    all_vals = [p for pts in data.values() for p in pts["prices"]] + list(buy_price_map.values())
    if all_vals:
        lo = math.floor(min(all_vals) / 0.05) * 0.05
        hi = math.ceil(max(all_vals) / 0.05) * 0.05
        ax.set_ylim(bottom=lo, top=hi)
    ax.yaxis.set_major_locator(plt.MultipleLocator(0.05))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(0.01))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(round(x * 100))}p"))
    ax.grid(True, linestyle="-", alpha=0.35, which="minor")
    ax.grid(True, linestyle="-", alpha=0.6, which="major")
    ax.set_axisbelow(True)
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    ax.set_title("Steam Market Prices")
    ax.legend(bbox_to_anchor=(1.06, 1), loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    all_times = [t for pts in data.values() for t in pts["times"]]
    if all_times:
        t_min = min(all_times)
        t_max = max(all_times)
        d = datetime(t_min.year, t_min.month, t_min.day) + timedelta(days=1)
        while d < t_max:
            ax.axvline(x=d, color="gray", alpha=0.8, linewidth=1)
            d += timedelta(days=1)
    fig.autofmt_xdate()
    plt.tight_layout()
    return fig


def show_graph():
    try:
        import matplotlib
        from matplotlib import cbook
        if not hasattr(cbook, "_Stack") and hasattr(cbook, "Stack"):
            cbook._Stack = cbook.Stack
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is required for graphing. Install with: pip install matplotlib")
        wait()
        return
    fig = _build_graph()
    if fig is None:
        wait()
        return
    plt.show()
    wait()


def export_graph():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is required for graphing. Install with: pip install matplotlib")
        wait()
        return
    fig = _build_graph()
    if fig is None:
        wait()
        return
    plt.savefig("steammarketprices.png", dpi=2400)
    plt.close()
    time.sleep(1)
    os.startfile("steammarketprices.png")
    wait()


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Steam Market API Script Help")
        print("-" * 25)
        print("Usage: python steammarketapi.pyw [option]")
        print("\nOptions:")
        print("  --graph       - Validates CSV and shows a price graph")
        print("  --export      - Validates CSV and saves graph to PNG")
        print("  --register   - Add new items to the script")
        print("  --unregister - Remove items from the script")
        print("  --clone       - Create a clone of the script with base settings")
        print("  --help        - Show this help menu")
        wait()
        sys.exit(0)

    if "--clone" in sys.argv:
        _clone_script()
        wait()
        sys.exit(0)

    if "--export" in sys.argv:
        validate_csv()
        export_graph()
        sys.exit(0)

    if "--graph" in sys.argv:
        validate_csv()
        show_graph()
        sys.exit(0)

    if "--unregister" in sys.argv:
        for cfg in DEFAULT_GAMES.values():
            cfg["items"] = _norm(cfg["items"])
        choices = []
        name_cache = {}
        for game_key, config in DEFAULT_GAMES.items():
            aid = config["app_id"]
            if aid not in name_cache:
                name_cache[aid] = get_app_name(aid) or game_key
            gname = name_cache[aid]
            for item in config["items"]:
                choices.append((game_key, gname, item["name"]))
        if not choices:
            print("No registered items.")
            sys.exit(0)
        print("Registered items:")
        for i, (_, gname, iname) in enumerate(choices, 1):
            print(f"{i}. [{gname}] {iname}")
        print(f"{len(choices) + 1}. Cancel")
        c = input("Choose item to unregister: ").strip()
        if not c.isdigit():
            sys.exit(0)
        n = int(c)
        if n < 1 or n > len(choices):
            sys.exit(0)
        game_key, game_name, item_name = choices[n - 1]
        for cfg in DEFAULT_GAMES.values():
            if cfg["app_id"] == DEFAULT_GAMES[game_key]["app_id"]:
                cfg["items"] = [i for i in cfg["items"] if i["name"] != item_name]
                break
        for k in list(DEFAULT_GAMES):
            if not DEFAULT_GAMES[k]["items"]:
                del DEFAULT_GAMES[k]
        content = open(__file__, encoding="utf-8").read()
        start = content.index("DEFAULT_GAMES = {")
        depth = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        content = content[:start] + _fmt_games() + content[end:]
        open(__file__, "w", encoding="utf-8").write(content)
        if os.path.isfile(CSV_FILE):
            rows = []
            with open(CSV_FILE, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                for row in reader:
                    if any(v.strip() for v in row):
                        rows.append(row)
            new_rows = [r for r in rows if not (r[1] == game_name and r[2] == item_name)]
            if len(new_rows) < len(rows):
                with open(CSV_FILE, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(REQUIRED_HEADERS)
                    w.writerows(new_rows)
                print(f"Removed {len(rows) - len(new_rows)} CSV entries")
        print(f"Unregistered: {item_name}")
        wait()
        sys.exit(0)

    if "--register" in sys.argv:
        game_keys = list(DEFAULT_GAMES.keys())
        name_cache = {}
        for i, key in enumerate(game_keys, 1):
            cfg = DEFAULT_GAMES[key]
            if cfg["app_id"] not in name_cache:
                name_cache[cfg["app_id"]] = get_app_name(cfg["app_id"]) or key
            print(f"{i}. {name_cache[cfg['app_id']]} ({cfg['app_id']})")
        print(f"{len(game_keys) + 1}. Custom")
        game_choice = input("Choose: ").strip()

        if game_choice.isdigit():
            n = int(game_choice)
            if 1 <= n <= len(game_keys):
                app_id = str(DEFAULT_GAMES[game_keys[n - 1]]["app_id"])
            elif n == len(game_keys) + 1:
                app_id = input("Steam app ID: ").strip()
            else:
                print("Invalid choice")
                sys.exit(1)
        else:
            print("Invalid choice")
            sys.exit(1)

        app_name = get_app_name(app_id)
        if app_name:
            print(f"Game: {app_name}")
            FALLBACK_NAMES[app_id] = app_name
        else:
            print(f"App ID: {app_id} (could not fetch name)")

        raw = input("Item name(s) (separate with ;): ").strip()
        item_names = [x.strip() for x in raw.split(";") if x.strip()]

        if not item_names:
            print("No items entered.")
            sys.exit(1)

        valid = []
        for item_name in item_names:
            if not item_exists(item_name, int(app_id)):
                print(f"Warning: '{item_name}' not found on market.")
                c = input("Register anyway? (y/n): ").strip().lower()
                if c == "y":
                    valid.append(item_name)
            else:
                valid.append(item_name)

        if not valid:
            print("No items to register.")
            sys.exit(0)
        item_names = valid

        item_names = list(dict.fromkeys(item_names))

        for cfg in DEFAULT_GAMES.values():
            if cfg["app_id"] == int(app_id):
                for existing in cfg["items"]:
                    ename = existing["name"] if isinstance(existing, dict) else existing
                    if ename in item_names:
                        print(f"Duplicate skipped: {ename}")
                        item_names.remove(ename)

        buy_prices = {}
        for item_name in item_names:
            bp = input(f"Buy price for '{item_name}' (blank for not bought): ").strip()
            if bp:
                try:
                    buy_prices[item_name] = _to_float(bp)
                except ValueError:
                    print("Invalid price, treating as not bought.")
                    buy_prices[item_name] = 0
            else:
                buy_prices[item_name] = 0

        if not item_names:
            print("No new items to register.")
            sys.exit(0)

        for cfg in DEFAULT_GAMES.values():
            if cfg["app_id"] == int(app_id):
                cfg["items"] = _norm(cfg["items"])
                for n in item_names:
                    cfg["items"].append({"name": n, "buy_price": buy_prices.get(n, 0)})
                break
        else:
            key = app_id
            items = [{"name": n, "buy_price": buy_prices.get(n, 0)} for n in item_names]
            DEFAULT_GAMES[key] = {"app_id": int(app_id), "items": items}

        content = open(__file__, encoding="utf-8").read()
        start = content.index("DEFAULT_GAMES = {")
        depth = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        # Update both DEFAULT_GAMES and FALLBACK_NAMES sections
        replacements = [
            (start, end, _fmt_games()),
            (fallback_start, fallback_end, _fmt_fallbacks())
        ]
        # Replace blocks from end to start to maintain index integrity
        replacements.sort(key=lambda x: x[0], reverse=True)
        
        for r_start, r_end, r_text in replacements:
            content = content[:r_start] + r_text + content[r_end:]
            
        open(__file__, "w", encoding="utf-8").write(content)

        for item_name in item_names:
            bp = buy_prices.get(item_name, 0)
            p_str = f" @ £{bp:.2f}" if bp else ""
            print(f"Registered: app_id={app_id}, item={item_name}{p_str}")
        print("Restart script to see changes")
        wait()
        sys.exit(0)

    validate_csv()

    for cfg in DEFAULT_GAMES.values():
        cfg["items"] = _norm(cfg["items"])

    name_cache = {}
    all_failures = []
    all_profitable = []
    for game_key, config in DEFAULT_GAMES.items():
        aid = config["app_id"]
        if aid not in name_cache:
            name_cache[aid] = get_app_name(aid) or game_key
        name = name_cache[aid]
        items = config["items"]
        total = len(items)
        fetched = []
        for i, item in enumerate(items, 1):
            print(f"[{name}: {i}/{total}] Fetching...", end="\r")
            price, error = get_steam_price(item["name"], app_id=aid)
            save_to_csv(name, item["name"], price)
            fetched.append((item["name"], price, error))
            if price:
                bp = item.get("buy_price", 0)
                if bp > 0:
                    be = _break_even(bp)
                    price_f = _to_float(price)
                    if price_f >= be:
                        all_profitable.append((name, item["name"], price, bp, be))
            else:
                all_failures.append((name, item["name"], error))
            if i < total:
                pass

        fetched.sort(key=lambda x: -_to_float(x[1]))
        for item, price, error in fetched:
            if price:
                print(f"\r{'':<50}\r[{name}] {item}: {price}")
            else:
                print(f"\r{'':<50}\r[{name}] {item}: Failed")
                print(f"  -> Reason: {error}")
        print()

    if all_failures:
        lines = [f"[{g}] {n}: {e}" for g, n, e in all_failures]
        _show_dialog("Fetch Failures", "\n".join(lines), "error")

    if all_profitable:
        lines = [f"[{g}] {n}\n  Price: {p} | Bought: £{b:.2f} | Break-even: £{be:.2f}" for g, n, p, b, be in all_profitable]
        _show_dialog("Items Above Break-Even", "\n\n".join(lines), "info")

    wait()
