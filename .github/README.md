# GitHub Actions Setup

## Required Secrets

To enable automated deployments, add these secrets in **Settings → Secrets and variables → Actions**:

### SSH_PRIVATE_KEY
Your private SSH key for accessing the server.

To get your private key:
```bash
cat ~/.ssh/id_rsa
# or
cat ~/.ssh/id_ed25519
```

Copy the entire output including `-----BEGIN ... KEY-----` and `-----END ... KEY-----`

### SERVER_HOST
```
5.78.143.44
```

### SERVER_USER
```
root
```

## How It Works

The workflow automatically triggers on:
- Push to `main` branch
- Manual trigger via Actions tab

It will:
1. SSH into the server
2. Pull latest code from GitHub
3. Rebuild the Go application
4. Restart the systemd service
5. Reload Caddy

## Manual Deployment

You can also trigger deployment manually from the Actions tab.
