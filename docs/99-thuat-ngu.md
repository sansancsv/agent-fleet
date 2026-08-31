# Đối chiếu thuật ngữ Anh – Việt

Nguyên tắc dùng trong toàn bộ tài liệu này: **giữ nguyên tiếng Anh** khi đó là
tên lệnh, tên tệp, tên sản phẩm, hoặc thuật ngữ mà mọi tài liệu tham chiếu đều
dùng tiếng Anh. Ở lần xuất hiện đầu tiên thì chú thích nghĩa trong ngoặc.

## Kiến trúc

| Tiếng Anh | Tiếng Việt | Ghi chú |
|---|---|---|
| control plane | tầng điều khiển | nơi ra quyết định định tuyến |
| execution plane | tầng thực thi | nơi agent chạy thật |
| capability plane | tầng năng lực | nơi kết nối ra hệ thống ngoài |
| distribution plane | tầng phân phối | nơi đóng gói và phát hành |
| gateway | cổng vào | giữ nguyên khi nói về OpenClaw Gateway |
| binding | luật định tuyến | ánh xạ (kênh, tài khoản, người) → agent |
| workspace | không gian làm việc | thư mục riêng của một agent |
| session | phiên | ngữ cảnh hội thoại có trạng thái |
| checkpoint | điểm lưu / điểm dừng | tuỳ ngữ cảnh: lưu trạng thái hay chờ người |
| checkpointer | bộ lưu trạng thái | thành phần LangGraph ghi state xuống DB |
| fan-out | phát tán song song | chạy nhiều agent cùng lúc trên một đầu vào |
| worktree | cây làm việc | `git worktree`, giữ nguyên tên lệnh |

## Quy trình

| Tiếng Anh | Tiếng Việt |
|---|---|
| deterministic workflow | quy trình xác định |
| non-deterministic workflow | quy trình phi xác định |
| orchestration | điều phối |
| human-in-the-loop | có người tham gia / chờ người duyệt |
| escalation | leo thang (chuyển lên cấp cao hơn) |
| guardrail | hàng rào an toàn |
| circuit breaker | cầu dao (tự ngắt khi lỗi liên tục) |
| idempotent | chạy nhiều lần cho cùng kết quả |
| definition of done | tiêu chí hoàn thành |

## Bảo mật

| Tiếng Anh | Tiếng Việt |
|---|---|
| prompt injection | chèn lệnh qua prompt |
| threat model | mô hình mối đe doạ |
| blast radius | phạm vi thiệt hại |
| least privilege | đặc quyền tối thiểu |
| defense in depth | phòng thủ nhiều lớp |
| allowlist / denylist | danh sách cho phép / danh sách chặn |
| audit log | nhật ký kiểm toán |
| secret rotation | xoay vòng khoá bí mật |
| sandbox | môi trường cách ly (giữ nguyên "sandbox") |
| data classification | phân loại mức nhạy cảm dữ liệu |
| zero retention | không lưu giữ dữ liệu (cam kết của nhà cung cấp model) |
| data sovereignty | chủ quyền dữ liệu |

## Vai trò agent

| Tiếng Anh | Tiếng Việt |
|---|---|
| orchestrator | điều phối viên |
| architect | kiến trúc sư |
| implementer | lập trình viên hiện thực |
| reviewer | thẩm định viên |
| tester | kỹ sư kiểm thử |
| security | kỹ sư bảo mật |
| SRE (site reliability engineer) | kỹ sư vận hành độ tin cậy |
| analyst | chuyên viên phân tích |

## Vận hành

| Tiếng Anh | Tiếng Việt |
|---|---|
| incident | sự cố |
| postmortem | báo cáo sau sự cố |
| blameless | không quy trách nhiệm cá nhân |
| rollback | quay lui phiên bản |
| feature flag | cờ tính năng |
| release gate | cổng phát hành |
| runbook | sổ tay vận hành |
| on-call | trực hệ thống |
| SEV1 / SEV2 / SEV3 | mức nghiêm trọng 1/2/3 |

## Từ viết tắt giữ nguyên

`ACP` (Agent Client Protocol), `MCP` (Model Context Protocol),
`ADR` (Architecture Decision Record), `RBAC`, `PVC`, `CI/CD`, `NDJSON`,
`OPA` (Open Policy Agent), `SAST`, `DSN`, `TTL`.
