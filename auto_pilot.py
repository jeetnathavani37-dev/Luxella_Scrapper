"""
auto_pilot.py

Push + Sync + Image-backfill teeno ko ek CONTINUOUS LOOP mein chalata
hai - ek hi GitHub Actions job mein, bina baar-baar naye workflow-runs
trigger kiye. Jab tak kisi bhi step mein kuch bhi pending/changed nahi
milta (matlab poora catalog fully synced/pushed/imaged ho chuka hai),
tab tak chalta rehta hai. GitHub Actions job max ~6 ghante tak chal
sakta hai - isliye MAX_RUNTIME_MINUTES thoda kam (5h40m) rakha hai,
safety margin ke liye.

Kaam kaise karta hai:
- Har round mein: shopify_push.run() -> shopify_sync.run() ->
  shopify_image_backfill.run() - teeno call hote hain, har ek apna
  BATCH_SIZE env var use karta hai
- Agar teeno se total kaam (pushed + synced-changed + images-processed)
  0 aaye - matlab genuinely sab kuch complete hai, loop khud ruk jaata
  hai
- Agar max runtime cap hit ho jaaye (backlog bohot bada hai), loop
  gracefully ruk jaata hai - agli scheduled run (jo already automatic
  hai) continue kar degi

Requires GitHub Secrets (sab already existing hain):
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN,
    SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Env vars (optional, defaults reasonable hain):
    PUSH_BATCH_SIZE (default 500 - chhota rakha hai taaki loop ke
        andar kai chhote rounds hon, ek bada round nahi jo bicch mein
        crash ho jaaye)
    SYNC_BATCH_SIZE (default 500)
    IMAGE_BATCH_SIZE (default 300)

Usage:
    python auto_pilot.py
"""
import os
import time
from datetime import datetime, timedelta

MAX_RUNTIME_MINUTES = 340  # ~5h40m, GitHub Actions 6h limit se safe margin


def run():
    # Har script apna BATCH_SIZE apne module-level se leta hai (os.environ
    # read hota hai import ke time) - isliye import se PEHLE set karna hai.
    os.environ.setdefault("BATCH_SIZE", "500")

    start = datetime.now()
    round_num = 0
    total_pushed = 0
    total_synced = 0
    total_imaged = 0

    while (datetime.now() - start) < timedelta(minutes=MAX_RUNTIME_MINUTES):
        round_num += 1
        print(f"\n{'=' * 25} ROUND {round_num} {'=' * 25}")
        print(f"Elapsed: {(datetime.now() - start).total_seconds() / 60:.1f} min")

        # Har round mein fresh import - kyunki har script apna access
        # token khud generate karta hai (24h validity), koi stale-state
        # issue nahi hoga import-once se, lekin BATCH_SIZE alag set karna
        # ho toh yahan os.environ change kar sakte hain per-phase.
        os.environ["BATCH_SIZE"] = os.environ.get("PUSH_BATCH_SIZE", "500")
        import shopify_push
        import importlib
        importlib.reload(shopify_push)
        print("\n--- PUSH phase ---")
        pushed = shopify_push.run() or 0
        total_pushed += pushed

        os.environ["BATCH_SIZE"] = os.environ.get("SYNC_BATCH_SIZE", "500")
        import shopify_sync
        importlib.reload(shopify_sync)
        print("\n--- SYNC phase ---")
        synced = shopify_sync.run() or 0
        total_synced += synced

        os.environ["BATCH_SIZE"] = os.environ.get("IMAGE_BATCH_SIZE", "300")
        import shopify_image_backfill
        importlib.reload(shopify_image_backfill)
        print("\n--- IMAGE BACKFILL phase ---")
        imaged = shopify_image_backfill.run() or 0
        total_imaged += imaged

        round_total = pushed + synced + imaged
        print(f"\nRound {round_num} summary: pushed={pushed}, synced={synced}, imaged={imaged}")

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
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run()
