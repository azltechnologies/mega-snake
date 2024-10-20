bqInstancesByDeploymentId() {
  local ARRAYS=()
  for arg in "$@"; do
    local INSTANCE_LIST=$(gcloud compute instances list --project hd-product-discovery-stage --filter="labels.deployment-id=$arg AND (status=RUNNING OR status=TERMINATED)" --format="value(id)" || true)
    ws_advice "ProjectId: $arg"
    echo "$INSTANCE_LIST"
    local INSTANCES=("${(f)INSTANCE_LIST}")
    local ARRAYS=(${INSTANCES[@]} ${ARRAYS[@]})
    ws_info "elements at the moment: ${#ARRAYS[@]}"
  done
  local result=${(j:" OR ":)ARRAYS}
  local result="resource.labels.instance_id=(\"$result\")"
  local result="resource.type=\"gce_instance\"\n$result"
  echo $result | pbcopy
  ws_success "success: Command copied to clipboard"
}
ws_tip "bqInstancesByDeploymentId" "get a bq command to get all the instances by deployment id"