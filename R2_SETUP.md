# Cloudflare R2 Video Storage Setup Guide

## Overview

RacePilot uses Cloudflare R2 for video storage. R2 is an S3-compatible object storage service with **zero egress fees**, making it ideal for video streaming.

## Why R2?

- **Zero bandwidth costs** - No fees for video streaming/downloads
- **Affordable storage** - $0.015/GB/month (cheaper than S3)
- **Global CDN** - Fast video delivery worldwide via Cloudflare's network
- **S3-compatible** - Standard API, easy to migrate if needed
- **Scales infinitely** - Works for 10 users or 10,000 users

## Cost Estimate

**Storage**: 100 users × 10 videos × 200MB = 200GB = **$3/month**
**Bandwidth**: Unlimited streaming = **$0/month** (no egress fees)
**Total**: **~$3/month** vs ~$93/month on AWS S3

---

## Step 1: Create Cloudflare Account

1. Go to [https://dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up)
2. Create a free account
3. Verify your email

## Step 2: Enable R2

1. In Cloudflare dashboard, click **R2** in the left sidebar
2. Click **Purchase R2 Plan**
3. Choose the **Free plan** (includes 10GB storage + 1M requests/month)
   - Or pay-as-you-go for production ($0.015/GB/month)

## Step 3: Create R2 Bucket

1. Click **Create bucket**
2. Bucket name: `racepilot-videos` (or your preferred name)
3. Location: Choose **Automatic** (Cloudflare picks optimal location)
4. Click **Create bucket**

## Step 4: Generate API Tokens

1. Click **Manage R2 API Tokens** (top right)
2. Click **Create API token**
3. Token name: `RacePilot Backend`
4. Permissions:
   - **Object Read & Write** (allows upload/download/delete)
5. Bucket restrictions:
   - Select **Apply to specific buckets only**
   - Choose `racepilot-videos`
6. Click **Create API Token**
7. **IMPORTANT**: Copy and save these values immediately (shown only once):
   - **Access Key ID** (looks like: `abc123def456...`)
   - **Secret Access Key** (looks like: `xyz789uvw012...`)
   - **Endpoint URL** (looks like: `https://<account-id>.r2.cloudflarestorage.com`)

## Step 5: Configure Railway Environment Variables

### Option A: Railway Dashboard (Recommended)

1. Go to [https://railway.app/dashboard](https://railway.app/dashboard)
2. Select your `racepilot-backend` project
3. Click on the service
4. Go to **Variables** tab
5. Add these variables:

```
VIDEO_STORAGE_TYPE=r2
R2_ENDPOINT_URL=https://<your-account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<your-access-key-id>
R2_SECRET_ACCESS_KEY=<your-secret-access-key>
R2_BUCKET_NAME=racepilot-videos
```

6. Click **Save** - Railway will auto-redeploy

### Option B: Railway CLI

```bash
cd C:\rp\racepilot-backend
railway login
railway variables set VIDEO_STORAGE_TYPE=r2
railway variables set R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
railway variables set R2_ACCESS_KEY_ID=<your-access-key-id>
railway variables set R2_SECRET_ACCESS_KEY=<your-secret-access-key>
railway variables set R2_BUCKET_NAME=racepilot-videos
```

## Step 6: Deploy

The code is already updated to use R2 storage automatically when `VIDEO_STORAGE_TYPE=r2` is set.

```bash
cd C:\rp\racepilot-backend
git add .
git commit -m "Add Cloudflare R2 video storage integration"
git push
```

Railway will auto-deploy the changes.

---

## Verification

### 1. Check Backend Logs

In Railway dashboard, view logs for:
```
[VideoStorage] Using R2 storage: bucket=racepilot-videos
```

### 2. Test Video Upload

1. Go to RacePilot dashboard
2. Upload a test video to a session
3. Verify it streams correctly in the replay page

### 3. Check R2 Dashboard

In Cloudflare R2 dashboard:
1. Open your bucket
2. You should see uploaded videos in `videos/` folder

---

## Optional: Custom Domain (Advanced)

For better branding and avoiding presigned URLs, you can set up a custom domain.

### Benefits:
- Videos served from `videos.race-pilot.app` instead of Cloudflare URLs
- No URL expiration (public bucket)
- Better SEO and branding

### Setup:

1. In R2 bucket settings, click **Settings**
2. Under **Public access**, click **Allow Access**
3. Add custom domain:
   - Domain: `videos.race-pilot.app`
   - DNS: Cloudflare will auto-configure if domain is on Cloudflare
4. Update Railway environment variable:
```
R2_PUBLIC_URL=https://videos.race-pilot.app
```

**Security Note**: This makes all videos publicly accessible via the custom domain. Users still need authentication to view through the API, but direct URLs bypass auth. Only enable if needed.

---

## Troubleshooting

### Error: "R2 storage requires R2_ENDPOINT_URL..."

**Solution**: Make sure all R2 environment variables are set in Railway dashboard.

### Error: "NoSuchBucket"

**Solution**:
1. Verify bucket name matches exactly in R2 dashboard and `R2_BUCKET_NAME` variable
2. Ensure API token has access to the bucket

### Error: "AccessDenied"

**Solution**:
1. Regenerate API token with **Object Read & Write** permissions
2. Update `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` in Railway

### Videos not appearing

**Solution**:
1. Check Railway logs for upload errors
2. Verify R2 bucket contains videos (check Cloudflare dashboard)
3. Check browser console for CORS errors

---

## Migration from Local Storage

If you previously used local storage, videos stored locally will be lost on Railway restarts. To migrate:

1. Download videos from current Railway container (if accessible)
2. Re-upload through the dashboard UI
3. Or: Write a migration script to copy from database `file_path` to R2

---

## Monitoring & Costs

### View R2 Usage

1. Cloudflare dashboard → R2 → Analytics
2. Monitor:
   - **Storage** (GB used)
   - **Class A operations** (uploads/deletes - $4.50 per million)
   - **Class B operations** (downloads/lists - $0.36 per million)

### Estimated Costs by Scale

| Users | Videos/User | Avg Size | Storage | Monthly Cost |
|-------|-------------|----------|---------|--------------|
| 100   | 10          | 200MB    | 200GB   | **$3**       |
| 1,000 | 10          | 200MB    | 2TB     | **$30**      |
| 10,000| 10          | 200MB    | 20TB    | **$300**     |

**Bandwidth**: $0 regardless of scale (R2's killer feature!)

---

## Support

- **Cloudflare R2 Docs**: [https://developers.cloudflare.com/r2/](https://developers.cloudflare.com/r2/)
- **RacePilot Code**: See `app/storage.py` and `app/routes/videos.py`
- **Issues**: Open a GitHub issue at your repository

---

## Summary

✅ Zero bandwidth costs for video streaming
✅ Affordable storage ($0.015/GB/month)
✅ Works with existing video playback code
✅ Automatic GPS sync maintained
✅ Scalable to thousands of users

Your video feature is now production-ready! 🎉
