$CLUSTER="qad"
$IMAGE="qad-backend:stable"
$NS="qad"

Write-Host "🚀 Starting QAD Deployment..."

docker builder prune -a --volumes -f
docker system prune -a --volumes -f

docker build -t $IMAGE .

docker images | Select-String qad-backend

kind delete cluster --name $CLUSTER
kind create cluster --name $CLUSTER

kind load docker-image $IMAGE --name $CLUSTER

kubectl config use-context "kind-$CLUSTER"

kubectl create namespace $NS --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/

Write-Host "⏳ Waiting for postgres..."
kubectl rollout status statefulset/postgres -n $NS --timeout=180s

Write-Host "⏳ Waiting for redis..."
kubectl rollout status deployment/redis -n $NS --timeout=120s

$deployments = @(
    "qad-web",
    "qad-celery",
    "qad-beat",
    "qad-daphne",
    "pgbouncer"
)

foreach ($d in $deployments) {
    Write-Host "♻️ Restarting $d"
    kubectl rollout restart deployment $d -n $NS
}

foreach ($d in $deployments) {
    Write-Host "⏳ Waiting for $d"
    kubectl rollout status deployment/$d -n $NS --timeout=180s
}

Write-Host "📊 Pods"
kubectl get pods -n $NS -o wide

Write-Host "🌐 Services"
kubectl get svc -n $NS

Write-Host "🔍 Deployments"
kubectl get deployments -n $NS -o wide