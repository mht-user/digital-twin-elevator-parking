# digital-twin-elevator-parking

## Tổng quan
Hệ thống mô phỏng dòng lưu chuyển của sinh viên nhằm phát hiện điểm nghẽn (bottleneck) tại khu vực nhà xe và thang máy. Dự án sử dụng Digital Twin để chạy các kịch bản dời lịch học, từ đó đưa ra phương án tối ưu giảm tải trong các khung giờ cao điểm.

## Cấu trúc thư mục
- `/docs`: Tài liệu đặc tả hệ thống (SRS), Test Plan.
- `/data`: Dataset giả lập (danh sách lớp, sức chứa nhà xe).
- `/se-simulation`: Logic chạy mô phỏng.
- `/optimization`: Thuật toán tính toán kịch bản tối ưu.
- `/frontend`: Giao diện Dashboard tương tác.
- `main.py`: Script điều phối và chạy kịch bản mô phỏng chính.

## Thành viên tham gia
- Đoàn Anh Tú - Optimization Engineer
- Mai Huyền Trâm - System Analyst (QA, Test, Docs)
- Trần Hoàng Trung - Data Engineer
- Đỗ Mỹ Trang - Simulation Engineer
- Dương Phúc An - Frontend Engineer
