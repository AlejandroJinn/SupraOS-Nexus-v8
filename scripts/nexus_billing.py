# nexus_billing.py — Stripe Integration for KlawAqua Nexus
import os, json, sys, time

KLAWAQUA = "/opt/klawaqua"
sys.path.insert(0, f"{KLAWAQUA}/scripts")

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

router = APIRouter(prefix="/billing", tags=["billing"])

# ── Plans ──────────────────────────────────────────────
PLANS = {
    "starter": {"name":"Starter","price":5000,"currency":"eur","interval":"month",
                "features":["11 modelos locales","3 cloud free","60 req/min","Soporte email"]},
    "pro": {"name":"Pro","price":20000,"currency":"eur","interval":"month",
            "features":["Todos los modelos","Cloud prioritario","300 req/min","Soporte prioritario","API streaming"]},
    "enterprise": {"name":"Enterprise","price":50000,"currency":"eur","interval":"month",
                   "features":["Fine-tuned models","SLA 99.9%","Req ilimitadas","Soporte 24/7","On-premise option","Custom integrations"]},
}

# ── Stripe init (lazy) ────────────────────────────────
def _stripe():
    try:
        import stripe
        key = os.environ.get("STRIPE_SECRET_KEY","")
        if not key:
            cfg = f"{KLAWAQUA}/config/api_keys.json"
            if os.path.exists(cfg):
                with open(cfg) as f:
                    key = json.load(f).get("stripe_secret_key","")
        if key:
            stripe.api_key = key
        return stripe, key
    except Exception as e:
        return None, ""

@router.get("/plans")
def list_plans():
    return {"plans": PLANS, "currency": "eur"}

@router.post("/checkout")
def create_checkout(plan: str, email: str = ""):
    stripe, key = _stripe()
    if not key or not stripe:
        # Simulation mode — no real Stripe
        session_id = f"sim_{plan}_{int(time.time())}"
        return {"simulation": True, "plan": plan, "session_id": session_id,
                "url": f"http://localhost:9095/billing/success?session_id={session_id}",
                "message": "Modo simulación — configura STRIPE_SECRET_KEY para producción"}
    try:
        p = PLANS.get(plan)
        if not p:
            return {"error": "Plan no existe"}
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": p["currency"], "product_data": {"name": p["name"]},
                          "unit_amount": p["price"]}, "quantity": 1}],
            mode="subscription",
            success_url=f"http://localhost:9095/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"http://localhost:9095/billing/cancel",
            customer_email=email or None,
        )
        return {"session_id": session.id, "url": session.url}
    except Exception as e:
        return {"error": str(e)}

@router.get("/success")
def checkout_success(session_id: str = ""):
    return {"status": "success", "session_id": session_id, "message": "Suscripción activada en SupraOS"}

@router.get("/cancel")
def checkout_cancel():
    return {"status": "cancelled", "message": "Pago cancelado — vuelve cuando quieras"}

@router.post("/webhook")
async def stripe_webhook(request: Request):
    stripe, key = _stripe()
    if not key or not stripe:
        return {"simulation": True, "message": "Webhook recibido en modo simulación"}
    payload = await request.body()
    sig = request.headers.get("stripe-signature","")
    try:
        event = stripe.Webhook.construct_event(payload, sig, os.environ.get("STRIPE_WEBHOOK_SECRET",""))
        return {"received": True, "type": event["type"]}
    except Exception as e:
        return {"error": str(e)}

@router.get("/status")
def billing_status(api_key: str = ""):
    return {"simulation": True, "plans_available": list(PLANS.keys()),
            "message": "Configura STRIPE_SECRET_KEY para activar pagos reales"}
