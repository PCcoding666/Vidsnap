import { Button } from "@/components/ui/button";
import { Video, LogOut, User } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate, useLocation } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

const Header = () => {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  
  const isLoginPage = location.pathname === '/login';
  const isMainApp = location.pathname === '/app'; // 判断是否在主应用页面
  
  const handleSignOut = async () => {
    await signOut();
    navigate('/login');
  };
  
  const getUserInitials = () => {
    if (!user?.email) return 'U';
    return user.email.charAt(0).toUpperCase();
  };
  return (
    <header className={`fixed top-0 left-0 right-0 z-50 border-b ${
      isMainApp 
        ? 'border-border/20 bg-background/95 backdrop-blur-sm' // 主应用：更轻量的背景
        : 'border-border/40 bg-background/80 backdrop-blur-lg' // 首页：营销风格
    }`}>
      <div className={isMainApp ? 'px-4' : 'container mx-auto px-4 sm:px-6 lg:px-8'}>
        <div className={`flex items-center justify-between ${
          isMainApp ? 'h-14' : 'h-16' // 主应用页面高度更小
        }`}>
          <div className="flex items-center gap-2">
            <div className={`flex items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent ${
              isMainApp ? 'h-8 w-8' : 'h-9 w-9' // 主应用Logo更小
            }`}>
              <Video className={isMainApp ? 'h-4 w-4 text-primary-foreground' : 'h-5 w-5 text-primary-foreground'} />
            </div>
            <span className={`font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent ${
              isMainApp ? 'text-lg' : 'text-xl' // 主应用文字更小
            }`}>
              Vidsnap
            </span>
          </div>
          
          {/* 仅在首页显示导航链接 */}
          {!isMainApp && (
            <nav className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                Features
              </a>
              <a href="#how-it-works" className="text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                How It Works
              </a>
              <a href="#testimonials" className="text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                Testimonials
              </a>
            </nav>
          )}

          <div className="flex items-center gap-3">
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="relative h-9 w-9 rounded-full">
                    <Avatar className="h-9 w-9">
                      <AvatarFallback className="bg-gradient-to-br from-primary to-accent text-primary-foreground">
                        {getUserInitials()}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium leading-none">{user.email}</p>
                      <p className="text-xs leading-none text-muted-foreground">
                        免费版用户
                      </p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate('/app')}>
                    <User className="mr-2 h-4 w-4" />
                    我的视频
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleSignOut} className="text-red-600">
                    <LogOut className="mr-2 h-4 w-4" />
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              !isLoginPage && (
                <>
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    className="hidden sm:inline-flex"
                    onClick={() => navigate('/login')}
                  >
                    登录
                  </Button>
                  <Button 
                    size="sm" 
                    className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity shadow-lg"
                    onClick={() => navigate('/login')}
                  >
                    免费开始
                  </Button>
                </>
              )
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
