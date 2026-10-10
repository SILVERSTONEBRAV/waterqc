from pathlib import Path
import re

p = Path(__file__).with_name("views.py")
text = p.read_text(encoding="utf-8")

# Wire plant scope into helper call sites that only pass user.
patterns = [
    (r"_batch_display_queryset\(\s*self\.request\.user\s*\)", "_batch_display_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_batch_display_queryset\(\s*user\s*\)", "_batch_display_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_process_display_queryset\(\s*self\.request\.user\s*\)", "_process_display_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_process_display_queryset\(\s*user\s*\)", "_process_display_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_request_display_queryset\(\s*self\.request\.user\s*\)", "_request_display_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_request_display_queryset\(\s*user\s*\)", "_request_display_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_result_display_queryset\(\s*self\.request\.user\s*\)", "_result_display_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_result_display_queryset\(\s*user\s*\)", "_result_display_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_coa_display_queryset\(\s*self\.request\.user\s*\)", "_coa_display_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_coa_display_queryset\(\s*user\s*\)", "_coa_display_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_analysis_input_queryset\(\s*self\.request\.user\s*\)", "_analysis_input_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_analysis_input_queryset\(\s*request\.user\s*\)", "_analysis_input_queryset(request.user, plant_id=self.get_scope_plant_id())"),
    (r"_checklist_queryset\(\s*user\s*\)", "_checklist_queryset(user, plant_id=self.get_scope_plant_id())"),
    (r"_specification_queryset\(\s*self\.request\.user\s*\)", "_specification_queryset(self.request.user, plant_id=self.get_scope_plant_id())"),
    (r"_specification_queryset\(\s*request\.user\s*\)", "_specification_queryset(request.user, plant_id=self.get_scope_plant_id())"),
]

# _get_*_or_404 helpers take user - update them to accept plant_id
for name in ("_get_process_or_404", "_get_batch_or_404", "_get_request_or_404", "_get_result_or_404", "_get_coa_or_404"):
    text = text.replace(f"def {name}(\n    user,\n    pk,", f"def {name}(\n    user,\n    pk,\n    plant_id=None,")

# Inside those helpers, display queryset calls need plant_id forwarded - already handled if we replace _*_display_queryset(user) globally carefully.

# Avoid double plant_id kwargs
text2 = text
for pattern, repl in patterns:
    text2 = re.sub(pattern, repl, text2)

# Fix accidental doubles
text2 = text2.replace(
    "plant_id=self.get_scope_plant_id(), plant_id=self.get_scope_plant_id()",
    "plant_id=self.get_scope_plant_id()",
)
text2 = text2.replace(
    "plant_id=plant_id, plant_id=self.get_scope_plant_id()",
    "plant_id=plant_id",
)

# Helper or_404 functions should pass plant_id to display querysets
text2 = text2.replace(
    "_process_display_queryset(user, plant_id=self.get_scope_plant_id())",
    "_process_display_queryset(user, plant_id=plant_id)",
)
# Wait - only inside module-level _get_* functions. View methods should keep self.get_scope_plant_id().
# Revert view-context ones by restoring after helper defs... This is getting messy.

p.write_text(text2, encoding="utf-8")
print("done")
print("request_has_permission", text2.count("request_has_permission"))
