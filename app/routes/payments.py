"""
Payment and subscription management with Stripe
"""
import stripe
import os
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.db.models import User, Subscription
from app.auth import get_db, get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])

# Initialize Stripe
# Strip whitespace/newlines from API keys (Railway sometimes adds them)
stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
stripe.api_key = stripe_key.strip() if stripe_key else None
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

# Subscription plans (TEST MODE)
PLANS = {
    "pro_monthly": {
        "name": "RacePilot Pro Monthly",
        "price_id": "price_1STuv15SUcNBBXSmNa2F75LY",  # Test mode price ID (£7.99/month)
        "price": 7.99,
        "interval": "month"
    },
    "club_monthly": {
        "name": "RacePilot Club Monthly",
        "price_id": "price_1STuyh5SUcNBBXSmMLOfiwgh",  # Test mode price ID (£40/month)
        "price": 40.00,
        "interval": "month"
    }
}


class CreateCheckoutRequest(BaseModel):
    plan_id: str
    success_url: str
    cancel_url: str


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create Stripe checkout session for subscription"""

    if request.plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[request.plan_id]

    try:
        print(f"[CHECKOUT] Creating session for {current_user.email}, plan {request.plan_id}", flush=True)
        print(f"[CHECKOUT] Price ID: {plan['price_id']}", flush=True)
        print(f"[CHECKOUT] Stripe API key exists: {stripe.api_key is not None}", flush=True)
        print(f"[CHECKOUT] Stripe API key starts with: {stripe.api_key[:12] if stripe.api_key else 'NONE'}", flush=True)

        # Create Stripe checkout session
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': plan['price_id'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            metadata={
                'user_id': current_user.id,
                'plan_id': request.plan_id
            }
        )

        print(f"[CHECKOUT] Success! Session ID: {checkout_session.id}", flush=True)
        return {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }

    except stripe.error.StripeError as e:
        error_msg = f"Stripe {type(e).__name__}: {str(e)}"
        print(f"[CHECKOUT ERROR] {error_msg}", flush=True)
        if hasattr(e, 'json_body'):
            print(f"[CHECKOUT ERROR] JSON body: {e.json_body}", flush=True)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[CHECKOUT ERROR] Unexpected: {error_msg}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhooks for subscription events"""

    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Handle subscription created
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        plan_id = session['metadata']['plan_id']

        # Create subscription record
        subscription = Subscription(
            user_id=user_id,
            stripe_subscription_id=session['subscription'],
            plan_id=plan_id,
            status='active',
            current_period_end=datetime.fromtimestamp(
                session['subscription']['current_period_end']
            )
        )
        db.add(subscription)
        db.commit()

    # Handle subscription updated
    elif event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']

        # Update subscription status
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_data['id']
        ).first()

        if subscription:
            subscription.status = subscription_data['status']
            subscription.current_period_end = datetime.fromtimestamp(
                subscription_data['current_period_end']
            )
            db.commit()

    # Handle subscription cancelled
    elif event['type'] == 'customer.subscription.deleted':
        subscription_data = event['data']['object']

        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_data['id']
        ).first()

        if subscription:
            subscription.status = 'cancelled'
            db.commit()

    return {"status": "success"}


@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's current subscription status"""

    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == 'active'
    ).first()

    if not subscription:
        return {
            "subscribed": False,
            "plan": "free",
            "features": {
                "max_sessions": 5,
                "ai_coaching": False,
                "fleet_replay": False
            }
        }

    plan = PLANS.get(subscription.plan_id, {})

    return {
        "subscribed": True,
        "plan": subscription.plan_id,
        "status": subscription.status,
        "current_period_end": subscription.current_period_end,
        "features": {
            "max_sessions": -1,  # Unlimited
            "ai_coaching": True,
            "fleet_replay": True,
            "wind_analysis": True
        }
    }


@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel user's subscription"""

    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == 'active'
    ).first()

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription")

    try:
        # Cancel in Stripe
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            cancel_at_period_end=True
        )

        return {"message": "Subscription will cancel at period end"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans")
async def get_plans():
    """Get available subscription plans"""
    return PLANS
