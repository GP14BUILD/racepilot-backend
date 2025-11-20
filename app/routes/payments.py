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
        "interval": "month",
        "features": {
            "ai_coaching": True,
            "fleet_replay": True,
            "wind_analysis": True
        }
    },
    "club_monthly": {
        "name": "RacePilot Club Monthly",
        "price_id": "price_1STuyh5SUcNBBXSmMLOfiwgh",  # Test mode price ID (£40/month)
        "price": 40.00,
        "interval": "month",
        "features": {
            "ai_coaching": True,
            "fleet_replay": True,
            "wind_analysis": True
        }
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

    print(f"[WEBHOOK] Received webhook event", flush=True)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        print(f"[WEBHOOK] Event type: {event['type']}", flush=True)
    except Exception as e:
        print(f"[WEBHOOK ERROR] Validation failed: {str(e)}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))

    # Handle subscription created
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        plan_id = session['metadata']['plan_id']
        stripe_subscription_id = session['subscription']

        print(f"[WEBHOOK] checkout.session.completed for user {user_id}, plan {plan_id}", flush=True)
        print(f"[WEBHOOK] Stripe subscription ID: {stripe_subscription_id}", flush=True)

        # Fetch full subscription object from Stripe to get current_period_end
        try:
            stripe_subscription = stripe.Subscription.retrieve(stripe_subscription_id)

            print(f"[WEBHOOK] Retrieved subscription: {stripe_subscription.id}", flush=True)
            print(f"[WEBHOOK] ALL Subscription keys: {list(stripe_subscription.keys())}", flush=True)

            # Try to get current_period_end - it should be there
            if 'current_period_end' in stripe_subscription:
                period_end = stripe_subscription['current_period_end']
            else:
                # Fallback: use created + 30 days
                print(f"[WEBHOOK WARNING] current_period_end not found, using created + 30 days", flush=True)
                period_end = stripe_subscription['created'] + (30 * 24 * 60 * 60)

            print(f"[WEBHOOK] Period end timestamp: {period_end}", flush=True)

            # Get plan features
            plan_features = PLANS.get(plan_id, {}).get("features", {})
            print(f"[WEBHOOK] Plan features: {plan_features}", flush=True)

            # Create subscription record with feature flags
            subscription = Subscription(
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id,
                plan_id=plan_id,
                status='active',
                current_period_end=datetime.fromtimestamp(period_end),
                has_ai_coaching=plan_features.get("ai_coaching", False),
                has_fleet_replay=plan_features.get("fleet_replay", False),
                has_wind_analysis=plan_features.get("wind_analysis", False)
            )
            db.add(subscription)
            db.commit()

            print(f"[WEBHOOK] Subscription created successfully for user {user_id}", flush=True)
            print(f"[WEBHOOK] Features enabled: AI Coaching={subscription.has_ai_coaching}, Fleet Replay={subscription.has_fleet_replay}, Wind Analysis={subscription.has_wind_analysis}", flush=True)
        except Exception as e:
            print(f"[WEBHOOK ERROR] Failed to create subscription: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            raise

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
            # Remove feature access when subscription is cancelled
            subscription.has_ai_coaching = False
            subscription.has_fleet_replay = False
            subscription.has_wind_analysis = False
            db.commit()
            print(f"[WEBHOOK] Subscription cancelled and features disabled for user {subscription.user_id}", flush=True)

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
