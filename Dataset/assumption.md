# ASSUMPTION.md — Digital Twin Lite: Dữ liệu lịch học & bãi xe ĐH Kinh tế Quốc dân (NEU)

## 0. Phạm vi & vai trò (đọc trước khi dùng)
Vai trò **Data Engineer**: cung cấp dữ liệu **thô, mô tả hiện trạng** (lịch học hiện
tại + hạ tầng phòng học/nhà xe) một cách chính xác, nhất quán.


## 1. Hạ tầng giảng đường
| Toà | Số tầng | Phòng/tầng | Tổng phòng | Sức chứa/phòng (giả định) |
|---|---|---|---|---|
| A2 | 10 | 14 | 140 | 80–120 SV |
| B  | 3  | 8  | 24  | 40–60 SV |
| C  | 3  | 8  | 24  | 40–60 SV |
| D  | 5  | 8  | 40  | 60–90 SV |
| **Tổng** | | | **228 phòng** | |

Quy tắc đặt `room_id`: `<Toà>-<Tầng 2 chữ số><Số thứ tự phòng trong tầng, 2 chữ số>`, ví dụ
`D-0508` = toà D, tầng 5, phòng số 08 trong tầng. Mọi `room_id` trong cả
`rooms.csv` và `schedule.csv` đều khớp đúng `building`/`floor` tương ứng; không có 2 lớp dùng
chung 1 phòng trong cùng (ngày, ca); không có lớp nào vượt sức chứa phòng được xếp.

## 2. Ca học 
| Ca | Giờ học | Cửa sổ đến | Cửa sổ về |
|---|---|---|---|
| Ca1 | 06:45–09:25 | 06:15–06:45 | 09:25–09:55 |
| Ca2 | 09:35–12:15 | 09:05–09:35 | 12:15–12:45 |
| Ca3 | 13:00–15:40 | 12:30–13:00 | 15:40–16:10 |
| Ca4 | 15:50–18:30 | 15:20–15:50 | 18:30–19:00 |

SV đến trước giờ học 30 phút, rời trường trong vòng 30 phút sau khi tan ca (giả thiết). 

## 3. Sinh viên & phương tiện
- `motorbike_ratio` (0.75–0.95/lớp): tỷ lệ SV của lớp sử dụng xe máy đến trường. Core simulation tính `total_motorbikes = num_students × motorbike_ratio`.
- `dorm_ratio` (0.05–0.25/lớp): tỷ lệ SV của lớp đang ở KTX; hiện chỉ giữ làm metadata/tham số mở rộng và **không tham gia** phép tính số xe trong core simulation.
- Nhà xe chỉ nhận xe máy, chưa tính ô tô.
- `events.csv` có thêm `motorbike_ratio` riêng cho từng sự kiện — dữ liệu cần thiết để simulation
  chạy được, không phải một suy diễn về mức độ tắc.
- Việc phân bổ xe vào P1/P2/P3 là hành vi cần được Simulation Engineer mô hình hoá. Dataset chỉ cung cấp nguyên liệu thô (sĩ số, `motorbike_ratio`, building và khoảng cách từng toà đến từng nhà xe), không áp sẵn tỷ lệ phân bổ. Với core simulation, nên dùng một rule deterministic dựa trên khoảng cách để kết quả Before/After có thể so sánh ổn định.

## 4. Nhà xe — hạ tầng & khoảng cách vật lý (`parking.csv`)
| Nhà xe | Phục vụ khu vực | Sức chứa | Cổng vào/ra (Normal) | Thời gian/lượt (Normal) |
|---|---|---|---|---|
| P1 | Gần toà A2, B | 3.000 xe | 2 vào / 2 ra | Vào 3s (quẹt vé) / Ra 10s (thu tiền mặt) |
| P2 | Gần toà C, D | 3.000 xe | 2 vào / 2 ra | Vào 3s / Ra 10s |
| P3 | Gần khu KTX | 6.000 xe | 2 vào / 2 ra | Vào 3s / Ra 10s |

Khoảng cách đi bộ ước lượng (mét) từ mỗi toà đến mỗi nhà xe:

Các giá trị này đã được ghi trực tiếp trong `parking.csv` ở 4 cột `dist_from_A2_m`, `dist_from_B_m`, `dist_from_C_m`, `dist_from_D_m` để Simulation Engineer có thể đọc trực tiếp khi phân bổ xe.

| Từ toà \ Đến nhà xe | P1 | P2 | P3 |
|---|---|---|---|
| A2 | 150m | 650m | 900m |
| B  | 100m | 600m | 850m |
| C  | 650m | 120m | 820m |
| D  | 700m | 180m | 780m |

### Cột `scenario` trong `parking.csv` — chỉ còn 2 mức điều kiện vận hành hạ tầng
| scenario | Số cổng vào/ra | Thời gian xử lý/xe | Diễn giải |
|---|---|---|---|
| **Normal** | 2/2 mỗi nhà xe | 3s vào / 10s ra | Vận hành tiêu chuẩn |
| **Worst** | P1 còn 1/2 cổng ra (bảo trì); P2, P3 vẫn 2/2 | 4s vào / 12–13s ra (mưa) | Có sự cố hạ tầng + yếu tố thời tiết bất lợi, dùng khi mô phỏng kịch bản xấu (kết hợp thêm `events.csv` nếu muốn) |

2 mức này **không gắn với ngày cụ thể nào** trong `schedule.csv`. Simulation Engineer tự quyết
định dùng thông số `Normal` hay `Worst` cho khung (ngày, ca) đang mô phỏng, tuỳ giả định kịch bản.

## 5. `events.csv` — Sự kiện phát sinh ngoài lịch thường lệ
24 ca thi giữa kỳ (ví dụ điển hình cho sự kiện gây tăng đột biến nhu cầu): `event_id`, `event_name`,
`day_of_week`, `day_vn`, `shift`, `building`, `num_students`, `motorbike_ratio`. Không có `room_id`
vì ở mức mô phỏng nhà xe chỉ cần biết toà và số SV là đủ.

## 6. Cấu trúc & quan hệ giữa các file (xem chi tiết từng cột tại `data_dictionary.csv`)

```
classes.csv (class_id) ──┐
                          ├──< schedule.csv >──┐
rooms.csv (room_id) ─────┘                     │
                                                 └── (building) ── parking.csv (khoảng cách)
events.csv (độc lập, building) ── (building) ── parking.csv (khoảng cách)
```

- `schedule.csv.class_id` → khoá ngoại tới `classes.csv.class_id`
- `schedule.csv.room_id` → khoá ngoại tới `rooms.csv.room_id` (và `building`/`floor`/
  `room_capacity` trong `schedule.csv` luôn là bản sao chính xác từ `rooms.csv`, đã kiểm chứng)
- `events.csv.building` và `schedule.csv.building`/`parking.csv.dist_from_<building>_m` dùng
  chung 4 mã toà: `A2`, `B`, `C`, `D`

## 7. Bằng chứng "vấn đề có thật" (chỉ thống kê thô, không so sánh phương án nào)
| Ngày - Ca | Tổng SV đang học cùng lúc (cộng dồn 4 toà) |
|---|---|
| Thứ 2 - Ca1 | 3.189 |
| Thứ 4 - Ca1 | 2.853 |
| Thứ 6 - Ca3 | 2.443 |
| Thứ 4 - Ca3 | 2.386 |
| Thứ 2 - Ca3 | 2.028 |

Đây là phép đếm cơ học (SUM theo GROUP BY) từ `schedule.csv`, không phải nhận định "đây là
Peak/Worst".

## 8. Giới hạn của dataset
- Là dữ liệu **mô phỏng/tổng hợp**, không phải thời khoá biểu thật của NEU.
- Chưa mô hình hoá: xe đạp điện/xe đạp, SV đi bộ/xe buýt, ô tô giảng viên, ngày lễ/nghỉ, gửi xe
  ngoài trường.
- `events.csv` hiện chỉ có 1 bộ ví dụ (thi giữa kỳ, Thứ 2 - Ca2 - toà D); muốn thử kịch bản khác
  cần tạo thêm file cùng cấu trúc.
- Phân bố lượng xe đến/đi trong từng khung 30 phút không được áp đặt sẵn.
