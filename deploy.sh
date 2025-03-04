#!/bin/bash

# 스크립트 종료 시 오류 발생
set -e

# 현재 디렉토리
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 이미지 태그 설정
IMAGE_TAG=${1:-latest}
IMAGE_NAME="k8s-ai-agent:${IMAGE_TAG}"

echo "Building Docker image: ${IMAGE_NAME}"
docker build -t ${IMAGE_NAME} ${DIR}

# Kubernetes 클러스터가 로컬 Docker 이미지를 사용할 수 있는지 확인
# Minikube를 사용하는 경우 다음 명령을 실행
# eval $(minikube docker-env)

echo "Applying Kubernetes manifests"
kubectl apply -f ${DIR}/k8s/configmap.yaml
kubectl apply -f ${DIR}/k8s/secret.yaml
kubectl apply -f ${DIR}/k8s/rbac.yaml
kubectl apply -f ${DIR}/k8s/deployment.yaml
kubectl apply -f ${DIR}/k8s/ingress.yaml

echo "Deployment completed successfully!"
echo "You can access the API at: http://k8s-ai-agent.example.com (or your configured domain)"
echo "To check the status of the deployment, run: kubectl get pods -l app=k8s-ai-agent"
