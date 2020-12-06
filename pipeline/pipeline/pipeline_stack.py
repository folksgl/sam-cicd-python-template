from aws_cdk import (
    core,
    aws_s3 as s3,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as pipeline_actions,
    aws_codebuild as codebuild
)


class PipelineStack(core.Stack):
    """ PipelineStack defines the CI/CD pipeline for this application """

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here

        # Define the 'source' stage
        artifact_bucket = s3.Bucket(self, "ArtifactBucket")
        pipeline = codepipeline.Pipeline(self, "Pipeline", artifact_bucket=artifact_bucket)
        source_output = codepipeline.Artifact("SourceOutput")

        # Get the CodeStar Connection ARN from secrets manager
        connection_arn = core.SecretValue.secrets_manager(
            secret_id="folksgl_github_connection_arn",
            json_field="arn"
        ).to_string()

        # Set up the pipeline to be triggered by a webhook on the GitHub repo
        # for the code. Don't be fooled by the name, it's just a codestar
        # connection in the background. Bitbucket isn't involved.
        github_source = pipeline_actions.BitBucketSourceAction(
            action_name="Github_Source",
            connection_arn=connection_arn,
            repo="sam-cicd-python-template",
            owner="folksgl",
            branch="main",
            output=source_output
        )
        pipeline.add_stage(stage_name="Source", actions=[github_source])

        # Define the 'build' stage
        build_stage_output = codepipeline.Artifact("BuildStageOutput")
        build_project = codebuild.PipelineProject(
            scope=self,
            id="Build",
            environment_variables={"PACKAGE_BUCKET": codebuild.BuildEnvironmentVariable(
                value=artifact_bucket.bucket_name,
                type=codebuild.BuildEnvironmentVariableType.PLAINTEXT
            )},
            environment=codebuild.LinuxBuildImage.STANDARD_4_0
        )
        build_action = pipeline_actions.CodeBuildAction(
            action_name="Build",
            project=build_project,
            input=source_output,
            outputs=[build_stage_output]
        )
        pipeline.add_stage(stage_name="Build", actions=[build_action])

        # Define the 'deploy' stage
        stack_name = "gateway-service-python"
        change_set_name = f"{stack_name}-changeset"

        create_change_set = pipeline_actions.CloudFormationCreateReplaceChangeSetAction(
            action_name="CreateChangeSet",
            stack_name=stack_name,
            change_set_name=change_set_name,
            template_path=build_stage_output.at_path("packaged.yaml"),
            admin_permissions=True,
            run_order=1
        )
        execute_change_set = pipeline_actions.CloudFormationExecuteChangeSetAction(
            action_name="Deploy",
            stack_name=stack_name,
            change_set_name=change_set_name,
            run_order=2
        )
        pipeline.add_stage(
            stage_name="DevDeployment",
            actions=[create_change_set, execute_change_set]
        )
