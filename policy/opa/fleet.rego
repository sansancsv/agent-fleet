# =============================================================================
# Chính sách OPA — chốt cưỡng chế cuối cùng, đặt trước mọi lần gọi tool.
# -----------------------------------------------------------------------------
# Vì sao cần thêm một tầng nữa khi đã có cấu hình ở OpenClaw/acpx/mcporter?
# Vì ba tầng kia là CẤU HÌNH — người ta sửa được, và sửa nhầm được.
# Tầng này là CHÍNH SÁCH — nằm trong git, có test, review riêng, deploy riêng.
#
# Kiểm thử:  opa test policy/opa/
# =============================================================================
package fleet.authz

import rego.v1

default allow := false

# --- Quyền theo vai trò (phản chiếu tool-policy.yaml) ------------------------
role_capabilities := {
	"orchestrator": {"read", "search", "fetch", "exec", "agent"},
	"architect":    {"read", "search", "fetch", "write"},
	"implementer":  {"read", "search", "fetch", "write", "exec"},
	"tester":       {"read", "search", "write", "exec"},
	"reviewer":     {"read", "search"},
	"security":     {"read", "search", "exec"},
	"docs-writer":  {"read", "search", "fetch", "write"},
	"sre":          {"read", "search", "fetch", "exec"},
	"analyst":      {"read", "search", "fetch"},
}

# --- Mẫu lệnh bị cấm tuyệt đối, không có ngoại lệ ----------------------------
forbidden_command_patterns := [
	`git\s+push\s+.*--force`,
	`git\s+push\s+.*\+`,
	`rm\s+-rf\s+/`,
	`DROP\s+(TABLE|DATABASE|SCHEMA)`,
	`DELETE\s+FROM\s+\w+\s*;`,          # DELETE không có WHERE
	`TRUNCATE\s+`,
	`kubectl\s+delete`,
	`aws\s+s3\s+rb`,
	`curl\s+.*api\.(anthropic|openai)\.com`,   # bỏ qua tầng ghi log
	`(env|printenv|set)\s*\|\s*(curl|nc|wget)`, # tuồn biến môi trường ra ngoài
	`chmod\s+777`,
]

allow if {
	capability_allowed
	not command_forbidden
	data_class_allowed
	within_budget
}

capability_allowed if {
	caps := role_capabilities[input.role]
	input.capability in caps
}

command_forbidden if {
	some pattern in forbidden_command_patterns
	regex.match(pattern, input.command)
}

# --- Dữ liệu nhạy cảm chỉ được xử lý bởi model tự host ----------------------
allowed_backends := {
	"public":       {"claude", "codex", "gemini", "local-llm"},
	"internal":     {"claude", "codex", "gemini", "local-llm"},
	"confidential": {"claude", "local-llm"},
	"restricted":   {"local-llm"},
}

data_class_allowed if {
	backends := allowed_backends[input.data_class]
	input.backend in backends
}

within_budget if {
	input.spent_usd < input.budget_usd
}

# --- Lý do từ chối, để ghi vào nhật ký kiểm toán ----------------------------
deny_reason contains msg if {
	not capability_allowed
	msg := sprintf("Vai trò '%s' không có quyền '%s'", [input.role, input.capability])
}

deny_reason contains msg if {
	command_forbidden
	msg := sprintf("Lệnh khớp mẫu bị cấm: %s", [input.command])
}

deny_reason contains msg if {
	not data_class_allowed
	msg := sprintf("Backend '%s' không được xử lý dữ liệu mức '%s'", [input.backend, input.data_class])
}

deny_reason contains msg if {
	not within_budget
	msg := sprintf("Vượt ngân sách: đã dùng %.2f / %.2f USD", [input.spent_usd, input.budget_usd])
}
