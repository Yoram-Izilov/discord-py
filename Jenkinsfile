pipeline {
    agent any

    environment {
        IMAGE_NAME        = 'mydiscordbot'
        DISCORD_DATA_PATH = '/home/izilov/Desktop/discord-files'
    }

    stages {
        stage('Deploy') {
            steps {
                echo "Deploying with docker-compose..."
                sh 'docker-compose up --build -d'
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
