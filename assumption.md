# ASSUMPTION.md — Digital Twin Lite: Tối ưu lịch học & bãi xe ĐH Kinh tế Quốc dân (NEU)

## 0. Mục tiêu bộ dữ liệu
Bộ 3 file `classes.csv`, `schedule.csv`, `parking.csv` mô phỏng (digital twin lite) luồng sinh viên
đi xe máy ra/vào trường theo lịch học, nhằm phục vụ:
1. **Simulation** dòng xe đến/đi tại 3 nhà xe theo từng ca học.
2. **Chứng minh hiệu quả tối ưu hoá lịch học** bằng cách so sánh 2 phương án lịch:
   - `version = baseline`: lịch "hiện trạng" — dồn nhiều lớp vào Thứ 2/Thứ 4, ca 1/ca 3, thiên
     về toà A2 (gần nhà xe P1) → gây dồn ứ.
   - `version = optimized`: lịch sau khi tái sắp xếp — dàn đều ngày/ca/toà nhà và điều tiết bớt
     sinh viên KTX sang nhà xe P3 → giảm đỉnh tải.

Toàn bộ số liệu là **dữ liệu mô phỏng (synthetic)**, sinh bằng script Python có `random.seed(42)`
để tái lập được, không phải số liệu thật của trường.

---

## 1. Giả định về hạ tầng giảng đường
| Toà | Số tầng | Phòng/tầng | Tổng phòng | Sức chứa/phòng (giả định) |
|---|---|---|---|---|
| A2 | 10 | 14 | 140 | 80–120 SV (giảng đường lớn) |
| B  | 3  | 8  | 24  | 40–60 SV |
| C  | 3  | 8  | 24  | 40–60 SV |
| D  | 5  | 8  | 40  | 60–90 SV |
| **Tổng** | | | **228 phòng** | |

- Mỗi lớp học phần có 30–80 SV (random đều), luôn được xếp vào phòng có sức chứa ≥ số SV lớp đó
  (đã kiểm tra: 0 vi phạm trong dữ liệu sinh ra).
- `schedule.csv` đảm bảo **không trùng phòng** trong cùng (version, scenario, ngày, ca) — đã kiểm
  tra: 0 xung đột thật trên 1.400 dòng lịch.

## 2. Giả định về ca học
| Ca | Giờ học | Cửa sổ đến (arrival) | Cửa sổ về (departure) |
|---|---|---|---|
| Ca1 | 06:45–09:25 | 06:15–06:45 | 09:25–09:55 |
| Ca2 | 09:35–12:15 | 09:05–09:35 | 12:15–12:45 |
| Ca3 | 13:00–15:40 | 12:30–13:00 | 15:40–16:10 |
| Ca4 | 15:50–18:30 | 15:20–15:50 | 18:30–19:00 |

Giả định: SV đến trước giờ học 30 phút và rời trường trong vòng 30 phút sau khi tan ca (theo đề
bài). Simulation nên rải lượng xe đến/đi **đều hoặc lệch về cuối cửa sổ 30 phút** (SV thường đến
sát giờ) — cột `arrival_window_start/end` và `departure_window_start/end` trong `schedule.csv`
cho phép mô hình hoá cả hai cách.

## 3. Giả định về sinh viên & phương tiện
- Tổng quy mô toàn trường ≈ **32.000 SV** (theo đề bài). Bộ dữ liệu sinh **400 lớp học phần**
  thường lệ (tổng lượt SV/tuần ≈ 22.400, vì một SV thường chỉ xuất hiện trong 1 lớp/khung giờ được
  mô phỏng — đây là dữ liệu "lớp diễn ra trong ngày" phục vụ mô phỏng luồng đi lại, không phải danh
  sách tín chỉ đầy đủ của SV) + **24 ca thi giữa kỳ** (chỉ dùng cho kịch bản Worst).
- `motorbike_ratio` (tỷ lệ SV trong lớp đi xe máy đến trường): random 0.75–0.95/lớp — phản ánh đa
  số SV NEU đi xe máy, một phần đi xe buýt/xe đạp/đi bộ/ở KTX cạnh trường.
- `dorm_ratio` (tỷ lệ SV trong lớp ở KTX): random 0.05–0.25/lớp.
- Bãi xe chỉ nhận **xe máy**, chưa tính ô tô (theo đề bài).
- SV có xu hướng gửi xe ở 2 nhà xe **trong trường** (P1, P2) hơn nhà xe **KTX** (P3) dù ở KTX, vì
  thuận tiện di chuyển đến giảng đường:
  - **Baseline**: chỉ 20% lượt xe máy của SV-KTX chọn gửi ở P3, 80% vẫn chọn gửi ở P1/P2 gần toà
    học (gây quá tải P1/P2 không cần thiết).
  - **Optimized**: chính sách khuyến khích (vé ưu đãi/tuyến xe điện nội bộ giả định) nâng tỷ lệ
    SV-KTX chọn P3 lên 50%, giảm tải cho P1/P2 mà không ảnh hưởng SV không ở KTX.

## 4. Giả định về nhà xe (parking.csv)
| Nhà xe | Vị trí phục vụ | Sức chứa | Cổng vào | Cổng ra | Thời gian/lượt |
|---|---|---|---|---|---|
| P1 | Toà A2, B | 3.000 xe | 2 | 2 | Vào 3s (quẹt vé) / Ra 10s (thu tiền mặt) |
| P2 | Toà C, D | 3.000 xe | 2 | 2 | Vào 3s / Ra 10s |
| P3 | Khu KTX | 6.000 xe | 2 | 2 | Vào 3s / Ra 10s |

- Năng lực check-in tối đa/30 phút = `số cổng vào × 1800s / thời gian mỗi xe`.
  Ví dụ điều kiện thường: 2 cổng × 1800/3 = **1.200 xe/30 phút**.
- Năng lực check-out tối đa/30 phút (điều kiện thường) = 2 × 1800/10 = **360 xe/30 phút** — đây là
  nút thắt cổ chai lớn nhất vì thao tác thu tiền mặt chậm hơn nhiều so với quẹt vé vào.
- Toà nhà được gán vào **nhà xe gần nhất** (`primary_lot`): A2, B → P1; C, D → P2. Khoảng cách
  (m) trong cột `distance_building_to_primary_lot_m` là ước lượng đi bộ từ giảng đường đến nhà xe,
  dùng để mô hình hoá thời gian di chuyển bổ sung nếu cần.

## 5. Ba kịch bản Normal / Peak / Worst Case

| Kịch bản | Ngày áp dụng | Đặc điểm | Hạ tầng nhà xe |
|---|---|---|---|
| **Normal** | Thứ 3, Thứ 5, Thứ 6, Thứ 7 | Lịch phân bổ tương đối đều theo ca/toà nhà | Hoạt động bình thường (2 vào/2 ra, 3s/10s) |
| **Peak** | Thứ 2, Thứ 4 | Ngày cao điểm đầu/giữa tuần — nhiều lớp lý thuyết lớn dồn vào Ca1 & Ca3, tập trung ở toà A2 (baseline) | Hoạt động bình thường nhưng **nhu cầu (demand)** tăng mạnh do lịch dồn |
| **Worst** | Thứ 2 (trùng lịch thi giữa kỳ) | = lịch Thứ 2 của kịch bản Peak **+ 24 ca thi giữa kỳ chen ngang** (baseline: dồn hết vào Ca2, toà D) **+ trời mưa** (SV mặc áo mưa thao tác chậm hơn, tỷ lệ đi xe máy vẫn cao) **+ 1 cổng check-out P1 đang bảo trì** | P1: chỉ còn 1 cổng ra (thay vì 2); thời gian vào/ra tăng lên 4s/12–13s do trời mưa |

**Cách lọc dữ liệu theo kịch bản:** mỗi dòng của `schedule.csv` đã có sẵn cột `scenario`, chỉ cần
`WHERE scenario = 'Normal' | 'Peak' | 'Worst'` — không cần gộp/join thêm. Riêng kịch bản `Worst`
đã **bao gồm sẵn** toàn bộ lớp học thường lệ của Thứ 2 (nhân bản từ Peak) cộng với các lớp thi
`EVT0xx` (đánh dấu `is_event = Y`), nên có thể dùng trực tiếp không cần hợp nhất với `Peak`.

`parking.csv` cũng có cột `scenario` tương ứng — luôn lấy đúng hàng hạ tầng theo kịch bản đang mô
phỏng (vì năng lực nhà xe ở Worst thấp hơn Normal/Peak).

## 6. Bằng chứng dữ liệu cho thấy tối ưu hoá có tác dụng
Số liệu dưới đây được tính trực tiếp từ dataset (script `generate_dataset.py`, seed=42), quy đổi
lượng xe máy cần vào nhà xe trong khung 30 phút đầu ca cao điểm nhất:

**Kịch bản Peak — Ca1 (06:15–06:45), nhà xe P1 (gần A2, B):**
| Version | Xe máy cần vào ~30 phút | Năng lực check-in/30 phút | Mức vượt tải |
|---|---|---|---|
| baseline | **3.120 xe** | 1.200 xe | **≈ 260%** (quá tải nặng, ùn ứ kéo dài) |
| optimized | **1.327 xe** | 1.200 xe | ≈ 111% (gần sát năng lực, ùn ứ nhẹ, giảm mạnh so với baseline) |

→ Giảm ~**57%** lượng xe dồn về P1 trong khung giờ cao điểm nhất, nhờ (a) dàn đều lớp học theo
ngày/ca thay vì dồn vào A2-Ca1, và (b) cân bằng lại tỷ trọng lớp giữa cụm A2/B (→P1) và cụm C/D
(→P2) từ 70/30 (baseline) xuống gần 50/50 (optimized).

**Kịch bản Worst — Ca2 (09:05–09:35, trùng giờ vào thi), nhà xe P2 (gần C, D — nơi dồn ca thi):**
| Version | Xe máy cần vào ~30 phút | Năng lực check-in/30 phút (đã giảm do mưa) | Mức vượt tải |
|---|---|---|---|
| baseline | **1.678 xe** | 900 xe | ≈ 186% |
| optimized | **1.170 xe** | 900 xe | ≈ 130% |

→ Ngay cả trong kịch bản xấu nhất (hạ tầng bị giảm năng lực + sự kiện thi chen ngang), việc dàn
lịch thi ra 2 ca (Ca2/Ca4) và 2 toà (C/D) thay vì dồn hết vào Ca2-toà D giúp giảm ~**30%** đỉnh tải
so với baseline — chứng minh tối ưu hoá lịch vẫn có tác dụng giảm nghẽn dù không thể loại bỏ hoàn
toàn tình trạng quá tải khi hạ tầng bị suy giảm đồng thời.

*(SV có thể chạy lại `generate_dataset.py` hoặc viết script simulation riêng dùng trực tiếp 3 file
CSV để tái lập/mở rộng phân tích trên, ví dụ: mô phỏng hàng đợi (queue) theo giây bằng SimPy, tính
thời gian chờ trung bình, độ dài hàng đợi tối đa, % thời gian vượt sức chứa, v.v.)*

## 7. Cấu trúc & cách dùng các file

### `classes.csv` — Danh mục lớp học phần (không phụ thuộc thời gian)
| Cột | Ý nghĩa |
|---|---|
| class_id | Mã lớp học phần (LHP0001…, EVT001… cho ca thi) |
| course_code / course_name | Mã & tên học phần (dữ liệu minh hoạ) |
| department | Khoa/Viện phụ trách |
| group_no | Số thứ tự nhóm/ca |
| num_students | Sĩ số lớp (30–80, riêng ca thi 60–80) |
| motorbike_ratio | Tỷ lệ SV trong lớp đi xe máy đến trường |
| dorm_ratio | Tỷ lệ SV trong lớp ở KTX |
| sessions_per_week | Số buổi học/tuần của lớp (1 hoặc 2) |

### `schedule.csv` — Lịch học/thi đã xếp phòng, theo 2 version × 3 scenario (dữ liệu sim chính)
Các cột quan trọng phục vụ mô phỏng: `version`, `scenario`, `day_of_week`, `shift`,
`start_time`/`end_time`, `building`/`room_id`/`room_capacity`, `primary_lot`,
`motorbike_to_P1/P2/P3` (số xe máy của lớp đó phân bổ vào từng nhà xe),
`arrival_window_start/end`, `departure_window_start/end`, `is_event`.
→ Cộng dồn `motorbike_to_P1/P2/P3` theo `(scenario, version, day_of_week, shift)` sẽ ra **tổng nhu
cầu xe máy vào từng nhà xe theo từng khung giờ** — input trực tiếp cho simulation hàng đợi.

### `parking.csv` — Hạ tầng & năng lực nhà xe theo từng kịch bản
`scenario`, `parking_lot_id`, `capacity_slots` (sức chứa), `checkin_gates_open`/
`checkout_gates_open`, `checkin_sec_per_vehicle`/`checkout_sec_per_vehicle`,
`max_checkin_throughput_veh_per_30min`/`max_checkout_throughput_veh_per_30min` (đã tính sẵn),
`notes` (diễn giải bối cảnh kịch bản).

## 8. Giới hạn của dataset (cần lưu ý khi dùng)
- Đây là dữ liệu **mô phỏng/tổng hợp**, không phải số liệu thời khoá biểu thật của NEU — dùng để
  kiểm chứng phương pháp/luồng simulation, cần thay bằng dữ liệu thật trước khi ra quyết định vận
  hành thực tế.
- Chưa mô hình hoá: xe đạp điện/xe đạp, SV đi bộ/xe buýt, ô tô của giảng viên, ngày lễ/nghỉ, cũng
  như hành vi SV gửi xe ngoài trường (quán trà đá, bãi tư nhân quanh trường) — nếu muốn mô hình
  "xì hơi" áp lực ra khu vực dân cư xung quanh khi nhà xe quá tải, cần bổ sung thêm.
- Phân bố đến/đi trong cửa sổ 30 phút giả định là **input tự do cho simulation** (có thể chọn phân
  bố đều — uniform, hoặc lệch về cuối cửa sổ — SV đến sát giờ học, hàm mật độ tam giác…), dataset
  không áp đặt sẵn phân bố theo giây.
- Số liệu tối ưu ở mục 6 chỉ minh hoạ 1 khung giờ cao điểm nhất; khuyến nghị chạy simulation đầy
  đủ 24 khung ngày×ca để đánh giá toàn diện.
