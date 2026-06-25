"""Allowed values for classification fields (D9 — PROVISIONAL)."""
# TODO(values): PROVISIONAL — xác nhận theo danh mục case Salesforce/VinFast thật
# trước khi siết enum. Wave 0 freeze field-NAME; value-set siết sau, KHÔNG phá contract.
VEHICLE_TYPE = {"ô tô điện", "xe máy điện"}                                # G_1
VEHICLE_USAGE_TYPE = {"cá nhân", "kinh doanh/dịch vụ", "taxi (Xanh SM)"}   # G_2
CUSTOMER_TYPE = {"cá nhân", "doanh nghiệp", "đại lý"}                      # G_3
