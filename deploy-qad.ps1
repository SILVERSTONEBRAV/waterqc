$ErrorActionPreference = "Continue"

function Wait-Docker {
    Write-Host "Checking Docker daemon..."

    $maxRetries = 12
    $count = 0

    while ($count -lt $maxRetries) {
        try {
            docker info | Out-Null
            Write-Host "Docker is ready."
            return $true
        } catch {
            Write-Host "Docker not ready. Retrying..."
            Start-Sleep -Seconds 5
        }
        $count++
    }

    Write-Host "Docker failed to start. Restarting Docker Desktop..."

    taskkill /F /IM "Docker Desktop.exe" 2>$null
    taskkill /F /IM "com.docker.backend.exe" 2>$null
    taskkill /F /IM "com.docker.proxy.exe" 2>$null
    taskkill /F /IM "vpnkit.exe" 2>$null

    wsl --shutdown

    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    Start-Sleep -Seconds 60

    return Wait-Docker
}

function Reset-Kind {
    Write-Host "Resetting Kind cluster..."

    kind delete cluster --name qad 2>$null

    Start-Sleep -Seconds 5

    kind create cluster --name qad
}

function Build-Image {
    Write-Host "Building image..."

    docker build -t qad-backend:stable .

    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed"
    }
}

function Load-Image {
    Write-Host "Loading image into Kind..."

    $loaded = $false
    $attempt = 0

    while (-not $loaded -and $attempt -lt 5) {
        try {
            kind load docker-image qad-backend:stable --name qad
            $loaded = $true
        } catch {
            Write-Host "Load failed. Retrying..."
            Start-Sleep -Seconds 5
        }
        $attempt++
    }

    if (-not $loaded) {
        throw "Failed to load image into Kind"
    }
}

function Deploy-K8s {
    Write-Host "Applying Kubernetes manifests..."

    kubectl apply -f .\k8s\qad-ha.yaml

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Apply failed. Resetting cluster..."
        Reset-Kind
        kubectl apply -f .\k8s\qad-ha.yaml
    }
}

function Wait-Ready {
    Write-Host "Waiting for pods..."

    kubectl wait --for=condition=ready pod --all -n qad --timeout=180s
}

function Zero-Downtime-Rollout {
    Write-Host "Rolling deployments safely..."

    kubectl rollout restart deployment web -n qad
    kubectl rollout restart deployment celery -n qad
    kubectl rollout restart deployment celery-beat -n qad

    kubectl rollout status deployment web -n qad
    kubectl rollout status deployment celery -n qad
    kubectl rollout status deployment celery-beat -n qad
}

# ================= MAIN PIPELINE =================

Wait-Docker

docker context use desktop-linux

docker system prune -a --volumes -f

Build-Image

Reset-Kind

Load-Image

Deploy-K8s

Wait-Ready

Zero-Downtime-Rollout

kubectl get pods -n qad
kubectl get svc -n qad
kubectl get deployments -n qad

Write-Host "Deployment completed successfully."