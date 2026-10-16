output "vpc_id" {
  value = module.clinicflow.vpc_id
}

output "public_subnet_ids" {
  value = module.clinicflow.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.clinicflow.private_subnet_ids
}

output "nat_gateway_public_ip" {
  value = module.clinicflow.nat_gateway_public_ip
}

output "cluster_name" {
  value = module.clinicflow.cluster_name
}

output "cluster_endpoint" {
  value = module.clinicflow.cluster_endpoint
}

output "node_group_name" {
  value = module.clinicflow.node_group_name
}

output "ecr_repository_urls" {
  value = module.clinicflow.ecr_repository_urls
}

output "configure_kubectl" {
  value = module.clinicflow.cluster_name == null ? null : "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.clinicflow.cluster_name} --endpoint-url ${var.moto_endpoint}"
}
