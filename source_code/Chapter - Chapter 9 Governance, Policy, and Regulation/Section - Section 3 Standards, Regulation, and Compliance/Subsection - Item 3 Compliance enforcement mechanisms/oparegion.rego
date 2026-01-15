# Enforce that processing_location equals device certificate claim "region".
package edge.compliance.region

# Input schema:
# {
#   "device_cert": {"subject": "...", "claims": {"region": "eu-west-1"}},
#   "processing_request": {"target_location": "eu-west-1", "action": "inference"}
# }

default allow = false

allow {
  device_region := input.device_cert.claims["region"]
  request_loc := input.processing_request.target_location
  request_loc == device_region
}

# Deny with reason for audit logs
deny_reason[reason] {
  not allow
  device_region := input.device_cert.claims["region"]
  request_loc := input.processing_request.target_location
  reason := sprintf("processing location %v disagrees with device region %v", [request_loc, device_region])
}