bqInstancesByDeploymentId() {
  local ARRAYS=()
  local PROJECTS=("hd-product-discovery-dev" "hd-product-discovery-stage" "hd-product-discovery-prod")
  local ENVIRONMENT=0
  for arg in "$@"; do
    if [ "$ENVIRONMENT" -eq 0 ]; then
      # Check if the argument value is a number between 1 and 3, if not return an error
      if [[ "$arg" =~ ^[1-3]$ ]]; then
        local ENVIRONMENT=${PROJECTS[arg]}
        continue
      else
        ws_error "Invalid argument: $arg; must be a number between 1 and 3"
        return 1
      fi
    fi
    local INSTANCE_LIST=$(gcloud compute instances list --project $ENVIRONMENT --filter="labels.deployment-id=$arg AND (status=RUNNING OR status=TERMINATED)" --format="value(id)" || true)
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
ws_tip "bqInstancesByDeploymentId" "get a bq command to get all the instances by deployment id
    bqInstancesByDeploymentId <project> [ <deploymentID> ... ]
      Where deploymentID is a number between 1 and 3:
        1 - hd-product-discovery-dev
        2 - hd-product-discovery-stage
        3 - hd-product-discovery-prod"