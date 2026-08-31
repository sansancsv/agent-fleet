package fleet.authz_test

import data.fleet.authz
import rego.v1

base := {"role": "implementer", "capability": "write", "command": "npm test",
         "backend": "claude", "data_class": "internal", "spent_usd": 1.0, "budget_usd": 8.0}

test_implementer_duoc_ghi if {
	authz.allow with input as base
}

test_reviewer_khong_duoc_ghi if {
	not authz.allow with input as object.union(base, {"role": "reviewer"})
}

test_chan_force_push if {
	not authz.allow with input as object.union(base, {"command": "git push --force origin main"})
}

test_chan_curl_thang_api_model if {
	not authz.allow with input as object.union(base, {"command": "curl https://api.openai.com/v1/chat"})
}

test_du_lieu_han_che_chan_model_ngoai if {
	not authz.allow with input as object.union(base, {"data_class": "restricted", "backend": "claude"})
}

test_du_lieu_han_che_cho_model_noi_bo if {
	authz.allow with input as object.union(base, {"data_class": "restricted", "backend": "local-llm"})
}

test_vuot_ngan_sach_bi_chan if {
	not authz.allow with input as object.union(base, {"spent_usd": 9.0})
}
