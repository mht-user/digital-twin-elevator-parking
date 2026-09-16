# Checklist giao diện `run_optimizer.py` — Digital Twin Lite

Tài liệu này chốt cấu trúc hàm chuẩn cho module Optimizer (OE) để cắm
thẳng vào pipeline test (`test_pipeline.py`) của SE mà không cần sửa gì
thêm. Toàn bộ điều kiện bên dưới được test tự động — sai điều nào,
`test_oe_integration` / `test_full_pipeline` sẽ báo `[FAIL]` kèm dòng
`schedule_id` cụ thể.

## 1. Vị trí file & tên hàm (bắt buộc chính xác)

- File: **`run_optimizer.py`**, đặt cùng cấp với `run_simulation.py`.
- Hàm: **`optimize_schedule`**

```python
def optimize_schedule(
    schedule: list[dict],
    events: list[dict],
    parking: list[dict],
    scenario: str = "Normal",
) -> list[dict]:
    ...
```

SE import bằng đúng dòng này, nên tên file/hàm/tham số phải khớp y hệt
(phân biệt hoa-thường):

```python
from run_optimizer import optimize_schedule
```

## 2. Input

| Tham số    | Kiểu        | Schema (khóa dict) |
|------------|-------------|---------------------|
| `schedule` | `list[dict]`| giống hệt `schedule.csv`: `schedule_id, class_id, room_id, building, floor, room_capacity, day_of_week, shift, num_students, motorbike_ratio, dorm_ratio` |
| `events`   | `list[dict]`| giống hệt `events.csv`: `event_id, building, day_of_week, shift, num_students, motorbike_ratio` |
| `parking`  | `list[dict]`| giống hệt `parking.csv` (2 dòng/scenario × 4 bãi P1–P4) |
| `scenario` | `str`       | `"Normal"` hoặc `"Worst"` |

**Lưu ý bẫy:** `load_dataset()` đọc bằng `csv.DictReader` nên **mọi giá
trị đều là `str`**, kể cả số — `row["num_students"]` là `"50"` chứ không
phải `50`. Nếu tự ép kiểu để tính toán thì khi trả về vẫn giữ nguyên giá
trị (số hay chuỗi số đều được, test so sánh theo giá trị không theo kiểu).

## 3. Output

- Trả thẳng **`list[dict]`**, không bọc thêm trong tuple/dict/object khác.
- Mỗi dict **cùng schema hệt input** (đủ 11 khóa như bảng trên, không
  thêm/bớt khóa).
- Đây là schedule đã sắp lại vị trí một số session cho tối ưu hơn — vẫn
  chỉ là danh sách session, không phải log hay báo cáo.

## 4. Điều kiện bắt buộc (trích từ `assert_schedule_valid()`)

1. **Không tự ý sửa `schedule` đầu vào (in-place).** Phải tạo dict/list
   mới (`dict(row)` cho từng dòng), không được `return schedule` hay sửa
   thẳng lên các dict được truyền vào. Test chụp lại bản gốc trước khi
   gọi hàm và so sánh lại sau đó — sửa in-place sẽ bị bắt ngay cả khi
   list trả về là object khác.
2. **Giữ nguyên số session:** `len(output) == len(input schedule)`.
   Không thêm, không bớt buổi học nào — đó là việc của
   `make_what_if_schedule()` bên SE, không phải của optimizer.
3. **Giữ nguyên tập `schedule_id`:** mỗi `schedule_id` ở input phải xuất
   hiện đúng 1 lần ở output. Không sinh `schedule_id` mới, không bỏ sót,
   không trùng lặp. Optimizer chỉ **đổi vị trí** một session đã có
   (`day_of_week`, `shift`, `room_id` và 3 trường ăn theo phòng), không
   phải tạo session mới.
4. **Không đổi danh tính buổi học:** với mỗi `schedule_id`, các trường
   `class_id`, `num_students`, `motorbike_ratio`, `dorm_ratio` phải giữ
   nguyên y hệt trước/sau. Đổi phòng không làm đổi lớp hay sĩ số.
5. **Không xung đột phòng:** không có 2 dòng nào trùng
   `(day_of_week, shift, room_id)`.
6. **Không xung đột lịch của lớp:** không có `class_id` nào xuất hiện 2
   lần trong cùng `(day_of_week, shift)`.
7. **Phòng phải tồn tại & đủ sức chứa:** `room_id` phải có thật trong
   `rooms.csv`, và `num_students <= room_capacity` (theo capacity **thật**
   của phòng đó trong `rooms.csv`).
8. **Đồng bộ metadata copy từ `rooms.csv`:** nếu đổi `room_id`, phải cập
   nhật lại `building`, `floor`, `room_capacity` của dòng đó theo đúng
   phòng mới. Quên bước này thì `validate_data.py` sẽ FAIL ở lần chạy
   tiếp theo (nó so `schedule.building == rooms.building`, v.v. cho từng
   dòng) — đây là lỗi hay gặp nhất khi test với optimizer thật.

## 5. Không bắt buộc nhưng nên có

- **Objective không được tệ hơn trước.** `test_oe_integration` chạy lại
  `run_simulation_from_data()` trên cả schedule gốc và schedule đã tối
  ưu, so theo thứ tự ưu tiên: *(số dòng BOTTLENECK, tổng phần trăm quá
  tải, util lớn nhất)* — bộ sau phải ≤ bộ trước theo thứ tự đó.
- Idempotent: chạy optimizer trên chính output của nó không nên làm xấu
  thêm (không bắt buộc, chỉ là dấu hiệu tốt).

## 6. Bản tối thiểu hợp lệ (không tối ưu gì, chỉ đúng cấu trúc)

```python
def optimize_schedule(schedule, events, parking, scenario="Normal"):
    return [dict(row) for row in schedule]
```

Đây chính là nội dung file `run_optimizer.py` (bản giả) đang có sẵn
trong repo. **Khi code thật xong, ghi đè trực tiếp lên file này** — giữ
nguyên tên file `run_optimizer.py` và tên hàm `optimize_schedule` — thì
`test_pipeline.py` tự động dùng code thật, không cần sửa gì ở phía SE.

## 7. Tự kiểm tra trước khi gửi code

```bash
python3 run_optimizer.py      # chạy độc lập, in nhanh so BOTTLENECK trước/sau
python3 test_pipeline.py      # chạy toàn bộ 8 test, bao gồm 2 test OE ở trên
```

Nếu cả 8 test đều `[PASS]` thì đã khớp hợp đồng.
