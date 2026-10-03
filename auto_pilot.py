"""
auto_pilot.py

Push + Sync + Image-backfill + Background-removal chaaron ko ek
CONTINUOUS LOOP mein chalata hai - ek hi GitHub Actions job mein, bina
baar-baar naye workflow-runs trigger kiye. Jab tak kisi bhi step mein
kuch bhi pending/changed nahi milta (matlab poora catalog fully
synced/pushed/imaged/bg-removed ho chuka hai), tab tak chalta rehta
hai. GitHub Actions job max ~6 ghante tak chal sakta hai - isliye
MAX_RUNTIME_MINUTES thoda kam (5h40m) rakha hai, safety margin ke liye.

Kaam kaise karta hai:
- Har round mein: shopify_push.run() -> shopify_sync.run() ->
  shopify_image_backfill.run() -> shopify_bg_removal.run() - chaaron
  call hote hain, har ek apna BATCH_SIZE env var use karta hai
- Agar chaaron se total kaam (pushed + synced-changed + images-
  processed + bg-removed) 0 aaye - matlab genuinely sab kuch complete
  hai, loop khud ruk jaata hai
- Agar max runtime cap hit ho jaaye (backlog bohot bada hai), loop
  gracefully ruk jaata hai - agli scheduled run (jo already automatic
  hai) continue kar degi
- Kisi phase mein exception (e.g. Supabase statement timeout) aaye to
  traceback print hota hai, wo phase us round mein 0 count hota hai aur
  loop chalta rehta hai. Error wala round "sab complete" nahi maana
  jaata. MAX_CONSECUTIVE_ERROR_ROUNDS lagatar error rounds ke baad loop
  rukta hai aur exit code 1 deta hai (asli outage Actions mein dikhe)

Requires GitHub Secrets (sab already existing hain):
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN,
    SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Env vars (optional, defaults reasonable hain):
    PUSH_BATCH_SIZE (default 500 - chhota rakha hai taaki loop ke
        andar kai chhote rounds hon, ek bada round nahi jo bicch mein
        crash ho jaaye)
    SYNC_BATCH_SIZE (default 500)
    IMAGE_BATCH_SIZE (default 300)
    BG_REMOVAL_BATCH_SIZE (default 50 - background removal CPU-heavy
        hai, chhota batch rakha hai)

Usage:
    python auto_pilot.py
"""
import importlib
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

MAX_RUNTIME_MINUTES = 340  # ~5h40m, GitHub Actions 6h limit se safe margin
MAX_CONSECUTIVE_ERROR_ROUNDS = 5
ERROR_BACKOFF_SECONDS = 30  # error ke baad Supabase/Shopify ko thoda saans


def run_phase(label, module_name, batch_env, batch_default):
    """Ek phase chalao. Returns (count, failed) - exception pe (0, True),
    taaki ek timeout poore auto_pilot session ko na maare."""
    # Har script apna BATCH_SIZE module-level pe padhta hai - import/reload se PEHLE set karo
    os.environ["BATCH_SIZE"] = os.environ.get(batch_env, batch_default)
    print(f"\n--- {label} phase ---")
    try:
        # Har round mein fresh import - har script apna access token khud banata hai
        module = importlib.import_module(module_name)
        importlib.reload(module)
        return module.run() or 0, False
    except Exception:
        print(f"[PHASE ERROR] {label} fail hua - is round mein skip, loop chalta rahega:")
        traceback.print_exc(file=sys.stdout)
        return 0, True


def run():
    # Har script apna BATCH_SIZE apne module-level se leta hai (os.environ
    # read hota hai import ke time) - isliye import se PEHLE set karna hai.
    os.environ.setdefault("BATCH_SIZE", "500")

    start = datetime.now()
    round_num = 0
    total_pushed = 0
    total_synced = 0
    total_imaged = 0
    total_bg_removed = 0
    total_phase_errors = 0
    consecutive_error_rounds = 0
    gave_up = False

    while (datetime.now() - start) < timedelta(minutes=MAX_RUNTIME_MINUTES):
        round_num += 1
        print(f"\n{'=' * 25} ROUND {round_num} {'=' * 25}")
        print(f"Elapsed: {(datetime.now() - start).total_seconds() / 60:.1f} min")

        pushed, push_err = run_phase("PUSH", "shopify_push", "PUSH_BATCH_SIZE", "500")
        synced, sync_err = run_phase("SYNC", "shopify_sync", "SYNC_BATCH_SIZE", "500")
        imaged, image_err = run_phase("IMAGE BACKFILL", "shopify_image_backfill", "IMAGE_BATCH_SIZE", "300")
        bg_removed, bg_err = run_phase("BACKGROUND REMOVAL", "shopify_bg_removal", "BG_REMOVAL_BATCH_SIZE", "50")
        total_pushed += pushed
        total_synced += synced
        total_imaged += imaged
        total_bg_removed += bg_removed
        round_errors = sum([push_err, sync_err, image_err, bg_err])
        total_phase_errors += round_errors

        round_total = pushed + synced + imaged + bg_removed
        print(f"\nRound {round_num} summary: pushed={pushed}, synced={synced}, "
              f"imaged={imaged}, bg_removed={bg_removed}, phase_errors={round_errors}")

        if round_errors:
            consecutive_error_rounds += 1
            if consecutive_error_rounds >= MAX_CONSECUTIVE_ERROR_ROUNDS:
                print(f"\n*** Lagatar {consecutive_error_rounds} rounds mein errors - loop rok rahe hain. ***")
                gave_up = True
                break
            # Error wala round "sab complete" nahi hai - 0 kaam error ki wajah se bhi ho sakta hai
            time.sleep(ERROR_BACKOFF_SECONDS)
            continue
        consecutive_error_rounds = 0

        if round_total == 0:
            print("\n*** Sab kuch complete hai - kisi bhi step mein kuch bhi pending nahi mila. Loop rok rahe hain. ***")
            break

        time.sleep(3)  # chhota saans - Supabase/Shopify pe zyada pressure na pade lagatar
    else:
        print(f"\n*** Max runtime ({MAX_RUNTIME_MINUTES} min) hit - abhi bhi kaam baaki hai. "
              f"Agli scheduled run mein continue hoga. ***")

    print(f"\n{'=' * 60}")
    print(f"AUTO-PILOT SUMMARY ({round_num} rounds, "
          f"{(datetime.now() - start).total_seconds() / 60:.1f} min)")
    print(f"  Total pushed: {total_pushed}")
    print(f"  Total synced (changed): {total_synced}")
    print(f"  Total images processed: {total_imaged}")
    print(f"  Total backgrounds removed: {total_bg_removed}")
    print(f"  Phase errors: {total_phase_errors}")
    print(f"{'=' * 60}")
    return 1 if gave_up else 0


if __name__ == "__main__":
    sys.exit(run())
