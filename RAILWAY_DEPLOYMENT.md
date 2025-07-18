# Railway Deployment Guide

This guide explains how to deploy the Underground API to Railway.

## 🚀 Quick Deployment

### 1. Connect Your Repository

1. Go to [Railway](https://railway.app)
2. Create a new project
3. Connect your GitHub repository
4. Railway will automatically detect the Python application

### 2. Set Environment Variables

In your Railway project dashboard, go to **Variables** and set:

#### Required Variables:
```
PORT=8000  # Usually set automatically by Railway
```

#### Supabase Variables (Optional but recommended):
```
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
ENCRYPTION_KEY=your-secure-32-character-encryption-key
```

### 3. Deploy

Railway will automatically deploy when you push to your main branch.

## 🔧 Configuration Details

### Files Configured for Railway:

- **`railway.json`**: Deployment configuration
- **`requirements.txt`**: Python dependencies
- **`main.py`**: Application entry point with error handling

### Startup Process:

1. Railway builds the application using Nixpacks
2. Installs dependencies from `requirements.txt`
3. Starts the application with `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. The app gracefully handles missing Supabase configuration

## 🏥 Health Checks

The API includes robust health checking:

- **`/health`**: Shows application status and Supabase connectivity
- **`/`**: Shows loaded routers and available endpoints

Example health check response:
```json
{
  "status": "healthy",
  "service": "underground-api", 
  "environment": "railway",
  "loaded_routers": ["PDF Generator", "User Profiles", "Companies"],
  "supabase_configured": true,
  "supabase_connected": true
}
```

## 🐛 Troubleshooting

### Common Issues:

#### 1. Build Failures
- Check that all dependencies in `requirements.txt` are available
- Ensure Python version compatibility

#### 2. Startup Failures  
- Missing required environment variables
- Check Railway logs for specific error messages

#### 3. Supabase Connection Issues
- Verify environment variables are set correctly
- Check Supabase project is active
- Ensure service role key has proper permissions

### Checking Logs:

1. Go to your Railway project dashboard
2. Click on **Deployments**
3. Click on the latest deployment
4. View **Build Logs** and **Deploy Logs**

### Testing the Deployment:

```bash
# Check if the app is running
curl https://your-app.railway.app/health

# Check available endpoints  
curl https://your-app.railway.app/

# Test PDF generation (requires Supabase setup)
curl "https://your-app.railway.app/pdf/generate?ticket=12345&username=test&password=test"
```

## 🔒 Security Considerations

### Production Environment Variables:

1. **Generate a secure encryption key:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use Railway's Secret Variables:**
   - Mark sensitive variables as "secret" in Railway dashboard
   - Never commit secrets to your repository

3. **Supabase Security:**
   - Use service role key for server-side operations only
   - Set up proper RLS policies in Supabase
   - Rotate keys periodically

## 📊 Monitoring

### Built-in Monitoring:

- Railway provides built-in metrics and logs
- Health check endpoint for uptime monitoring
- Error tracking through application logs

### Custom Monitoring:

You can add external monitoring by hitting these endpoints:
- `GET /health` - Application health status
- `GET /` - Service information

## 🔄 Continuous Deployment

### Automatic Deployments:

Railway automatically deploys when you:
1. Push to your main branch
2. The build and tests pass
3. Environment variables are properly configured

### Manual Deployments:

1. Go to Railway dashboard
2. Click **Deploy Latest Commit**
3. Monitor deployment logs

## 📈 Scaling

### Railway Scaling Options:

1. **Vertical Scaling**: Increase memory/CPU in Railway dashboard
2. **Environment Variables**: Adjust for production load
3. **Database Connections**: Monitor Supabase connection limits

### Performance Tips:

1. Monitor Railway metrics dashboard
2. Optimize Supabase queries
3. Use connection pooling for high traffic
4. Cache frequently accessed data

## 💰 Cost Optimization

### Railway Pricing:

- Free tier available for development
- Pay-per-use for production
- Monitor usage in Railway dashboard

### Cost-Saving Tips:

1. Use environment variables to disable non-essential features in development
2. Monitor Supabase usage limits
3. Optimize API response sizes
4. Use Railway's sleep mode for development environments

## 🆘 Support

If you encounter issues:

1. **Check Railway Logs**: Look for specific error messages
2. **Test Locally**: Ensure the app works with your environment variables
3. **Railway Documentation**: [docs.railway.app](https://docs.railway.app)
4. **Railway Discord**: Active community support 