pipeline {
    agent any

    environment {
        IMAGE_NAME        = 'mydiscordbot'
        DISCORD_DATA_PATH = '/home/izilov/Desktop/discord-files'
    }

    stages {
        stage('Deploy Monitoring') {
            when { changeset 'monitoring/**' }
            environment {
                MONITORING_DEPLOY_PATH = '/home/izilov/Desktop/discord-monitoring'
            }
            steps {
                echo "Deploying monitoring stack..."
                withCredentials([
                    string(credentialsId: 'grafana-admin-password',
                           variable: 'GRAFANA_ADMIN_PASSWORD'),
                    string(credentialsId: 'discord-alertmanager-webhook-url',
                           variable: 'DISCORD_WEBHOOK_URL')
                ]) {
                    sh '''
                        rsync -a --delete monitoring/ "$MONITORING_DEPLOY_PATH/"
                        umask 133
                        printf "%s" "$DISCORD_WEBHOOK_URL" > "$MONITORING_DEPLOY_PATH/alertmanager/discord-webhook-url"
                        docker compose -p monitoring -f "$MONITORING_DEPLOY_PATH/docker-compose.yml" up -d
                    '''
                }
            }
        }

        stage('Deploy') {
            steps {
                echo "Deploying with docker-compose..."
                sh 'docker compose build && docker compose up -d'
            }
        }

        stage('Remove Dangling Images') {
            steps {
                script {
                    echo "Removing dangling images..."
                    def danglingImages = sh(script: 'docker images --filter "dangling=true" -q', returnStdout: true).trim()
                    if (danglingImages) {
                        sh "docker rmi ${danglingImages.replace('\n', ' ')}"
                    } else {
                        echo "No dangling images to remove."
                    }
                }
            }
        }

        stage('Verify Container Running') {
            steps {
                script {
                    sleep(time: 5, unit: 'SECONDS')
                    def status = sh(
                        script: "docker inspect --format='{{.State.Running}}' ${IMAGE_NAME}",
                        returnStdout: true
                    ).trim()
                    if (status != 'true') {
                        error "Container ${IMAGE_NAME} failed to start. Run: docker logs ${IMAGE_NAME}"
                    }
                    echo "Container ${IMAGE_NAME} is running successfully."
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline completed.'
        }
        success {
            echo 'Pipeline succeeded.'
        }
        failure {
            echo "Pipeline failed. Check logs with: docker logs ${IMAGE_NAME}"
        }
    }
}
