# Kubernetes AI Agent

This project implements an AI Agent using LangChain and Text2Cypher to analyze and process natural language commands related to Kubernetes cluster management.

## Features

- Natural language processing for Kubernetes operations
- Integration with Kubernetes API for cluster management
- Support for commands like:
  - Viewing namespace information
  - Finding resource-intensive pods/deployments
  - Scaling deployments

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```
   cp .env.example .env
   ```
   Then edit the `.env` file with your OpenAI API key and Neo4j credentials.

3. Run the application:
   ```
   python app.py
   ```

## Usage

Send natural language commands to the agent, such as:

1. "Show me namespace information for cluster1"
2. "Tell me which pod and deployment in suslmk-ns namespace is using the most CPU"
3. "Scale that deployment's replicas by 2x"

## Architecture

- `app.py`: Main application entry point
- `agent/`: Core agent functionality
- `k8s/`: Kubernetes API integration
- `models/`: Data models
- `utils/`: Utility functions

## Containerization and Kubernetes Deployment

### Docker Build

Build the Docker image:

```bash
docker build -t 44ce789b-kr1-registry.container.nhncloud.com/container-platform-registry/k8s-ai-agent:latest .
docker push 44ce789b-kr1-registry.container.nhncloud.com/container-platform-registry/k8s-ai-agent:latest
```

### Kubernetes Deployment

The project includes Kubernetes manifests for easy deployment:

1. **Prerequisites**:
   - Kubernetes cluster with RBAC enabled
   - kubectl configured to access your cluster
   - (Optional) Ingress controller installed

2. **Configuration**:
   - Update the ConfigMap in `k8s/configmap.yaml` with your settings
   - Update the Secret in `k8s/secret.yaml` with your API keys (base64 encoded)
   - Modify the Ingress host in `k8s/ingress.yaml` to match your domain

3. **Deployment**:
   Use the provided deployment script:
   ```bash
   ./deploy.sh [image-tag]
   ```
   Or apply the manifests manually:
   ```bash
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/secret.yaml
   kubectl apply -f k8s/rbac.yaml
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/ingress.yaml
   ```

4. **Verification**:
   ```bash
   kubectl get pods -l app=k8s-ai-agent
   kubectl get svc k8s-ai-agent
   ```

### Security Considerations

- The application requires access to the Kubernetes API
- RBAC is configured with least privilege principles
- Sensitive information is stored in Kubernetes Secrets
- Consider implementing additional security measures for production use

### Resource Requirements

- CPU: Minimum 100m, recommended 500m
- Memory: Minimum 256Mi, recommended 512Mi
- Storage: No persistent storage required

## Neo4j 설치 및 구성

본 프로젝트는 선택적으로 Neo4j 그래프 데이터베이스를 활용하여 Kubernetes 리소스 간의 관계를 효과적으로 분석할 수 있습니다.

### Neo4j Helm 차트를 사용한 설치

Neo4j를 Kubernetes 클러스터에 설치하려면 다음 단계를 따르세요:

1. **Helm 차트 설정 파일 생성**:
   `custom-values.yaml` 파일을 생성하여 다음 설정을 추가합니다:

   ```yaml
   neo4j:
     # 클러스터 이름 설정
     name: "neo4j"
     password: "password"  # 프로덕션 환경에서는 보안 비밀번호로 변경하세요
     resources:
       cpu: "500m"     # 최소 요구사항
       memory: "2Gi"   # 최소 요구사항
   volumes:
     data:
       mode: dynamic
       dynamic:
         storageClassName: "cp-storageclass"  # 클러스터의 스토리지 클래스에 맞게 조정
         accessModes:
           - ReadWriteOnce
         requests:
           storage: 10Gi
   ```

2. **Helm을 사용하여 Neo4j 설치**:
   ```bash
   helm install neo4j neo4j/neo4j-standalone -f custom-values.yaml --namespace default
   ```

3. **환경 변수 설정**:
   Neo4j를 사용하려면 `.env` 파일에서 다음 설정을 활성화하세요:
   ```
   USE_NEO4J=true
   NEO4J_URI=bolt://neo4j:7687  # Kubernetes 내부 서비스 이름 사용
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=password      # 위에서 설정한 비밀번호와 동일하게 설정
   ```

### Neo4j 사용 시 이점

- Kubernetes 리소스 간의 복잡한 관계 시각화
- 그래프 기반 쿼리를 통한 고급 분석 기능
- 리소스 종속성 및 영향 분석 향상