# =============================================================================
# Agent Fleet — lệnh vận hành. Chạy `make` để xem danh sách.
# =============================================================================
SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE := docker compose -f deploy/docker/docker-compose.yml --env-file .env

.PHONY: help
help:  ## Hiện danh sách lệnh
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Vòng đời ---------------------------------------------------------------
.PHONY: bootstrap
bootstrap:  ## Cài công cụ, sinh khoá, kiểm tra tiên quyết
	bash ./bootstrap.sh

.PHONY: up
up: validate oc-validate  ## Khởi động toàn bộ ngăn xếp
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory health

.PHONY: down
down:  ## Dừng ngăn xếp (giữ dữ liệu)
	$(COMPOSE) down

.PHONY: nuke
nuke:  ## Dừng và XOÁ HẾT dữ liệu (không thể hoàn tác)
	$(COMPOSE) down -v

.PHONY: logs
logs:  ## Theo dõi log (dùng: make logs S=openclaw-gateway)
	$(COMPOSE) logs -f $(S)

# --- Kiểm chứng -------------------------------------------------------------
.PHONY: oc-validate
oc-validate:  ## Kiểm chứng cấu hình OpenClaw bằng CHÍNH binary OpenClaw
	@bash ./scripts/oc-validate.sh

.PHONY: preflight
preflight:  ## Đối chiếu CLI thật đã cài với những gì repo giả định
	./scripts/preflight.sh

.PHONY: validate
validate:  ## Kiểm tra cú pháp và tính nhất quán của mọi cấu hình
	bash ./scripts/validate.sh

.PHONY: health
health:  ## Chờ và kiểm tra sức khoẻ các dịch vụ (có retry — không báo lỗi giả)
	@bash ./scripts/health.sh

.PHONY: audit
audit:  ## Chạy rà soát bảo mật của OpenClaw + test chính sách OPA
	$(COMPOSE) exec -T openclaw-gateway openclaw security audit
	opa test policy/opa/ -v

.PHONY: test
test:  ## Chạy test của bộ điều phối
	cd orchestration/langgraph && python -m pytest tests/ -q

# --- Vận hành ---------------------------------------------------------------
.PHONY: capability
capability:  ## Sinh lại các CLI từ MCP server sau khi sửa mcporter.json
	$(COMPOSE) exec -T mcporter bash /fleet/capability-plane/generate-clis.sh

.PHONY: tools
tools:  ## Xem TÊN TOOL CHÍNH XÁC của một server (dùng: make tools S=github)
	@test -n "$(S)" || { echo "Thiếu S=<tên server>"; exit 64; }
	$(COMPOSE) exec -T mcporter mcporter list $(S)

.PHONY: mcp-status
mcp-status:  ## Trạng thái kết nối của mọi MCP server
	$(COMPOSE) exec -T mcporter mcporter list

.PHONY: agents
agents:  ## Xem đội hình agent và luật định tuyến
	$(COMPOSE) exec -T openclaw-gateway openclaw agents list --tree
	$(COMPOSE) exec -T openclaw-gateway openclaw agents list --bindings

.PHONY: import-workflows
import-workflows:  ## Nhập workflow n8n từ git vào n8n
	$(COMPOSE) exec -T n8n n8n import:workflow --separate --input=/workflows

.PHONY: export-workflows
export-workflows:  ## Xuất workflow n8n ra git (chạy sau khi sửa trên giao diện)
	$(COMPOSE) exec -T n8n n8n export:workflow --all --separate --output=/workflows

.PHONY: publish-skills
publish-skills:  ## Xuất bản skill nội bộ lên ClawHub (dùng: make publish-skills V=1.2.0)
	cd distribution-plane/skills && bash ./publish.sh $(V)

# --- Chạy thử ---------------------------------------------------------------
.PHONY: demo-flow
demo-flow:  ## Chạy thử flow giao hàng tính năng
	$(COMPOSE) exec -T agent-runner acpx flow run /fleet/execution-plane/flows/feature-delivery.flow.ts \
	  --input-json '{"taskId":"DEMO-1","title":"Thêm health endpoint","repo":"/srv/repos/demo"}'

.PHONY: demo-review
demo-review:  ## Chạy thử thẩm định chéo ba model
	$(COMPOSE) exec -T agent-runner /fleet/execution-plane/scripts/fanout-review.sh /srv/repos/demo
