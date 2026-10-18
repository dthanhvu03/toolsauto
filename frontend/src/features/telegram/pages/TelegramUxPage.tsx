import type { ReactNode } from "react"
import { Send } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const COMMAND_GROUPS = [
  {
    title: "Luồng video",
    hint: "Dùng hằng ngày",
    commands: [
      ["/sansang", "Video chờ đăng"],
      ["/moi", "Video mới, nút Xử lý"],
      ["/nguon", "Quét ngay · Bật/Tắt"],
      ["/dadang", "Đã đăng, lùi nếu bấm nhầm"],
      ["/tai", "Chỉ tải bản gốc"],
      ["/caidat", "Cài đặt luồng video"],
    ],
  },
  {
    title: "Buffer",
    hint: "Hạn đăng và chỉ số",
    commands: [
      ["/han", "Tuần, hôm nay, tháng"],
      ["/so", "Hiện, cảm xúc, bình luận"],
    ],
  },
  {
    title: "Hệ thống",
    hint: "Worker",
    commands: [
      ["/status", "Đang chạy hay tạm dừng"],
      ["/health", "Sức khoẻ"],
      ["/pause", "Tạm dừng"],
      ["/resume", "Chạy tiếp"],
      ["/help", "Danh sách lệnh"],
    ],
  },
] as const

function KeyRow({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>
}

export function TelegramUxPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Cấu trúc Telegram</h1>
        <p className="text-sm text-muted-foreground">
          Đúng các màn bot đang gửi. Hàng trên là việc chính, hàng dưới là việc phụ.
        </p>
      </div>

      <Alert>
        <Send data-icon="inline-start" />
        <AlertTitle>Bài đã lên Facebook</AlertTitle>
        <AlertDescription>
          Nút Xóa chỉ gỡ bài chưa gửi. Buffer từ chối xóa bài đã đăng, nên reel trùng phải gỡ trên page.
        </AlertDescription>
      </Alert>

      <Tabs defaultValue="sansang">
        <TabsList>
          <TabsTrigger value="sansang">Sẵn sàng</TabsTrigger>
          <TabsTrigger value="buffer">Buffer</TabsTrigger>
          <TabsTrigger value="lenh">Lệnh</TabsTrigger>
        </TabsList>

        <TabsContent value="sansang" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Video đã chọn page</CardTitle>
              <CardDescription>#1059 · Mê Câu Cá</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Button className="w-full">Xếp vào Mê Câu Cá</Button>
              <KeyRow>
                <Button variant="outline" className="flex-1">
                  Đổi page
                </Button>
                <Button variant="outline" className="flex-1">
                  Đã đăng
                </Button>
              </KeyRow>
              <KeyRow>
                <Button variant="secondary" className="flex-1">
                  Gửi lại
                </Button>
                <Button variant="secondary" className="flex-1">
                  Chọn đoạn
                </Button>
                <Button variant="secondary" className="flex-1">
                  Chia phần
                </Button>
              </KeyRow>
            </CardContent>
            <CardFooter>Chưa chọn page thì hàng đầu là Chọn page, không có Đổi page.</CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="buffer" className="flex flex-col gap-4">
          <Card size="sm">
            <CardHeader>
              <CardTitle>Số từng bài</CardTitle>
              <CardDescription>
                /so liệt kê từng bài. Chi tiết mở đủ số của một bài. Ảnh, chữ và video dùng cùng bộ số.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <Badge>Video</Badge>
                <p className="text-muted-foreground">10 hiện · 1 cảm xúc · 0 bình luận · 0 chia sẻ · 2 bấm · 30%</p>
              </div>
              <div className="flex flex-col gap-1">
                <Badge variant="secondary">Ảnh</Badge>
                <p className="text-muted-foreground">Link .jpg .png .gif .webp. Chưa lên thì chưa có số.</p>
              </div>
              <div className="flex flex-col gap-1">
                <Badge variant="outline">Chữ</Badge>
                <p className="text-muted-foreground">Không file, chỉ caption. Nút Xếp vào của video vẫn gửi file video.</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Bài trong /han</CardTitle>
              <CardDescription>Đăng ngay ở ngoài. Xóa nằm sau Thêm và phải xác nhận.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <KeyRow>
                <Button className="flex-1">Đăng ngay</Button>
                <Button variant="outline" className="flex-1">
                  Chi tiết
                </Button>
              </KeyRow>
              <Button variant="secondary" className="w-full">
                Thêm
              </Button>
              <Separator />
              <div className="flex flex-col gap-2">
                <p className="text-sm font-medium">Thao tác thêm</p>
                <KeyRow>
                  <Button variant="outline" className="flex-1">
                    Lên đầu
                  </Button>
                  <Button variant="outline" className="flex-1">
                    Xuống cuối
                  </Button>
                </KeyRow>
                <KeyRow>
                  <Button variant="outline" className="flex-1">
                    Nháp
                  </Button>
                  <Button variant="outline" className="flex-1">
                    Nhân bản
                  </Button>
                </KeyRow>
                <Button variant="destructive" className="w-full">
                  Xóa
                </Button>
                <Button variant="destructive" className="w-full">
                  Xóa hẳn
                </Button>
              </div>
            </CardContent>
            <CardFooter>Bài lỗi hiện Đăng lại thay cho Đăng ngay. Cùng một nút gửi.</CardFooter>
          </Card>
        </TabsContent>

        <TabsContent value="lenh" className="flex flex-col gap-4">
          {COMMAND_GROUPS.map((group) => (
            <Card key={group.title} size="sm">
              <CardHeader>
                <CardTitle>{group.title}</CardTitle>
                <CardDescription>{group.hint}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {group.commands.map(([command, hint]) => (
                  <div key={command} className="flex items-center gap-2">
                    <Badge variant="secondary">{command}</Badge>
                    <span className="truncate text-muted-foreground">{hint}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  )
}
