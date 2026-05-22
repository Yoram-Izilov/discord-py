pipeline {
    agent any

    environment {
        IMAGE_NAME        = 'mydiscordbot'
        DISCORD_DATA_PATH = '/home/izilov/Desktop/discord-files'
    }

    stages {
        stage('Build Image') {
            steps {
                echo "Building ${IMAGE_NAME} image..."
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Stop Running Containers') {
            steps {
                echo "Stopping running discordbot containers..."
                sh 'docker ps -q --filter "name=discordbot" | xargs -r docker stop || true'
            }
        }

        stage('Remove Stopped Containers') {
            steps {
                echo "Removing stopped discordbot containers..."
                sh 'docker ps -aq --filter "name=discordbot" | xargs -r docker rm || true'
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

        stage('Run Container') {
            steps {
                sh '''
                    docker run -d \
                        --network monitoring_monitoring \
                        -e OTEL_EXPORTER_OTLP_ENDPOINT="tempo:4317" \
                        -v $DISCORD_DATA_PATH/:/app/data/ \
                        -v $DISCORD_DATA_PATH/config.json:/app/config/config.json \
                        --restart unless-stopped \
                        --name $IMAGE_NAME \
                        $IMAGE_NAME
                '''
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