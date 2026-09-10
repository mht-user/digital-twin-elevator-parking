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
- Việc phân bổ xe vào P1/P2/P3/P4 là hành vi cần được Simulation Engineer mô hình hoá. Dataset chỉ cung cấp nguyên liệu thô (sĩ số, `motorbike_ratio`, building và khoảng cách từng toà đến từng nhà xe), không áp sẵn tỷ lệ phân bổ. Với core simulation, nên dùng một rule deterministic dựa trên khoảng cách để kết quả Before/After có thể so sánh ổn định.

## 4. Nhà xe — hạ tầng & khoảng cách vật lý (`parking.csv`)
Các nhà xe được đặt ID theo đúng số thứ tự đã khoanh trên sơ đồ tham chiếu NEU do nhóm sử dụng:

| ID | Tên trong dataset | Vị trí tương đối trên sơ đồ | Sức chứa giả định |
|---|---|---|---:|
| P1 | Nha de xe so 1 | Bãi phía dưới khu giảng đường, gần cụm C/D | 3.000 xe |
| P2 | Nha de xe so 2 | Bãi dạng chữ L ở khu trung tâm, sát cụm B/D và gần A2 | 3.000 xe |
| P3 | Nha de xe so 3 | Bãi phía bên phải sơ đồ, gần khu Nhà 12 | 6.000 xe |
| P4 | Nha de xe so 4 | Bãi phía đông khu giảng đường, gần B2/cổng đi bộ | 3.000 xe |

Sức chứa vẫn là **tham số synthetic** của mô hình. Sơ đồ tham chiếu được dùng để chỉnh lại tên, vị trí tương đối và khoảng cách; không dùng để suy ra sức chứa thật.

### Khoảng cách ước lượng từ toà học tới nhà xe
Khoảng cách được ước lượng theo **tỷ lệ tương đối trên sơ đồ**, lấy mốc người dùng đề xuất `P1 -> A2 ≈ 200 m`, rồi làm tròn về bội số 10 m. Do sơ đồ không phải bản đồ đo đạc theo tỷ lệ chuẩn, các số này chỉ dùng cho mô phỏng hành vi chọn bãi.

| Từ toà \ Đến nhà xe | P1 | P2 | P3 | P4 |
|---|---:|---:|---:|---:|
| A2 | 200m | 100m | 300m | 200m |
| B  | 120m | 40m  | 240m | 120m |
| C  | 60m  | 100m | 200m | 100m |
| D  | 80m  | 40m  | 240m | 140m |

Các giá trị trên nằm trực tiếp trong `parking.csv` ở các cột `dist_from_A2_m`, `dist_from_B_m`, `dist_from_C_m`, `dist_from_D_m`.

Core Simulation nên phân bổ `total_motorbikes = num_students × motorbike_ratio` vào P1-P4 bằng một rule **deterministic** dựa trên khoảng cách. Gợi ý:

`weight_i = (1 / distance_i) / sum_j(1 / distance_j)`

`vehicles_i = total_motorbikes × weight_i`

Như vậy bãi gần hơn nhận tỷ trọng cao hơn, và cùng một input luôn cho cùng một kết quả Before/After.

### `scenario` trong `parking.csv` — chỉ là điều kiện vận hành hạ tầng
| scenario | Cổng vào/ra | Thời gian xử lý/xe | Diễn giải |
|---|---|---|---|
| **Normal** | 2/2 ở P1-P4 | 3s vào / 10s ra | Vận hành tiêu chuẩn |
| **Worst** | P1 còn 1/2 cổng ra; P2-P4 vẫn 2/2 | 4s vào / 12–13s ra | Thời tiết bất lợi + sự cố hạ tầng; có thể kết hợp `events.csv` khi stress test |

Hai mức này **không gắn với ngày cụ thể** trong `schedule.csv`. Peak/Bottleneck phải được Simulation Engineer suy ra từ demand và năng lực xử lý, không phải nhãn do Data Engineer gắn sẵn.

## 5. `events.csv` — Sự kiện phát sinh ngoài lịch thường lệ
24 ca thi giữa kỳ (ví dụ điển hình cho sự kiện gây tăng đột biến nhu cầu): `event_id`, `event_name`,
`day_of_week`, `day_vn`, `shift`, `building`, `num_students`, `motorbike_ratio`. Không có `room_id`
vì ở mức mô phỏng nhà xe chỉ cần biết toà và số SV là đủ.

## 6. Cấu trúc & quan hệ giữa các file (xem chi tiết từng cột tại `data_dictionary.csv`)

```
classes.csv (class_id) ──┐
                          ├──< schedule.csv >──┐
rooms.csv (room_id) ─────┘                     │
                                                 └── (building) ── parking.csv (P1-P4, khoảng cách)
events.csv (độc lập, building) ── (building) ── parking.csv (P1-P4, khoảng cách)
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
