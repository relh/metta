# ECR repository for episode-runner images
# CI pushes to both primary and eval account ECRs
# Eval cluster pulls from eval ECR (no cross-account pull needed)

resource "aws_ecr_repository" "episode_runner" {
  name                 = "episode-runner"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "episode_runner" {
  repository = aws_ecr_repository.episode_runner.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 30 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = {
        type = "expire"
      }
    }]
  })
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.episode_runner.repository_url
  description = "ECR repository URL for episode-runner images"
}
