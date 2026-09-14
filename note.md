C1: 5%  (16-13)
C2: 28% (33-16)
C3: 16% (44-34)
C4: 25% (59-44)
C5: 1% (59)
cấu trúc input

60% và 80%

1, thông số ra
2, input bao nhiêu cảnh bảo bất thường
3, cấu hình sau cảnh báo là gì, lý do
4, nếu đồng ý cập nhật ntn

1, Thông số được lấy ra gồm hệ số sử dụng tài nguyên của hệ thống nhưng phải đặt trong mẫu hoặc chuyển về mẫu dữ liệu theo dạng JSON như sau:

[
    // server 1
    {
        "ip hoặc tên host": "",
        "tỉ lệ sử dụng CPU": , 
        "tỉ lệ sử dụng RAM": ,
        "số lượng kết nối": ,
    },
    //server 2 tương tự ....
]

Dữ liệu phải có ít nhất 2 server vì 1 server không cần cân bằng tải. Có thể có thêm các thông số phụ như độ trễ mạng, thời gian phản hồi, ... nhưng như trên là đủ cho xác định cấu hình tải vì đã đủ phần tài nguyên chính là RAM và CPU cũng như số lượng kết nối là đủ để đánh giá và đưa ra cách cân bằng tải. Vì các phương thức cân bằng tải của Nginx lựa chọn phụ thuộc vào những thứ đó. 
Đồ án không xét với các phần cứng khác như bộ nhớ ngoài.
Chọn dạng % cho đơn vị CPU và RAM vì nó dễ đọc và chuẩn hóa. Ví dụ như lấy cảnh báo thì sử dụng ngưỡng % dễ hơn so với việc cân đo xem hệ thống sử dụng bao nhiêu đơn vị. Chưa chắc ngưỡng được đặt ở máy này cao thì máy kia cũng cao do khác biệt phần cứng. Hoặc người quản trị trước khi xác nhận chỉnh sửa với cấu hình được đề xuất thì cũng phải đọc lại xem với đề xuất này đã giải quyết được vấn đề chưa, thì đọc chỉ số % dễ hơn là "mức sử dụng/mức tổng".

Đầu vào để ở dạng JSON vì kiểu dữ liệu này cung cấp thông tin tốt hơn, chỉ cần dùng cặp {} là có thể phân tách được các server với nhau, và model cũng hiểu là đây là một danh sách chỉ số các server.

2, Input có mức bất thường khi CPU hoặc RAM có lượng sử dụng vượt mức 60% và 80% sẽ lần lượt được tính là cảnh báo mức vừa và mức cao. 

Chọn CPU và RAM vì đây là 2 tài nguyên máy chính của hệ thống. 
3, Cấu hình sau cảnh báo chọn 2 mốc 60 và 80. Vì với 60%, bình thường ở mức sử dụng ổn hoặc nhẹ nhàng thì hiếm khi dùng đến mức đó và đôi lúc lên trên 60% cũng bình thường nên chỉ để ở mức vừa, tùy xem có kéo dài không và có lên cận mức cao hơn không. Cũng vì vậy nên mức dùng nặng được đặt ở 80%. Mức 80 được chọn vì tài nguyên sử dụng là lớn và vẫn còn khoảng 20% để bộ phận tới hạn. Phần này sẽ câu thêm thời gian cho người quản trị hệ thống còn có thời gian xoay sở.

4, Nếu người dùng đồng ý cập nhật, agent đọc file rồi thay thế khối upstream trong cấu hình với phần được đề xuất. Lý do là vì do cấu hình Nginx và cách nó hoạt động, ngắn gọn thì phần cấu hình cân bằng tải của Nginx được đặt trong khối upstream{} trong file nginx.conf, đồ án đưa ra phần cấu hình đề xuất là áp dụng cho khối này.
(https://docs.nginx.com/nginx/admin-guide/load-balancer/http-load-balancer/#proxy_pass)