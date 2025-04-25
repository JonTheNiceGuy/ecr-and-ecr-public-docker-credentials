# AWS ECR and ECR-Public Docker Credentials Script

This script allows you to run a service which provides a docker-daemon with credentials for the AWS ECR and AWS ECR Public services. It is ONLY useful when
[docker-credential-ecr-login](https://github.com/awslabs/amazon-ecr-credential-helper) is not available on your target system.

For example, if your CI/CD system is unable to use the `ecr-login` script, then this might be helpful to run on the host OS, and share with the CI/CD system.

As specified in the opening lines of the script itself:

> I'm under no obligation to fix anything here or maintain this at all! Feel free to reuse any components of this in your own work without assigning any credit.
