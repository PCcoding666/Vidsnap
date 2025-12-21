import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Auth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/card';

const Login = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    // 如果已登录，重定向到应用主页
    if (user) {
      navigate('/app');
    }
  }, [user, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/20 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
            YouTube Video Analysis
          </h1>
          <p className="text-muted-foreground">Sign in to access your video history and premium features</p>
        </div>

        <Card className="p-6 shadow-xl">
          <Auth
            supabaseClient={supabase}
            appearance={{
              theme: ThemeSupa,
              variables: {
                default: {
                  colors: {
                    brand: 'hsl(var(--primary))',
                    brandAccent: 'hsl(var(--primary))',
                  },
                },
              },
              className: {
                container: 'w-full',
                button: 'w-full rounded-lg font-medium transition-all',
                input: 'rounded-lg',
              },
            }}
            providers={['google']}
            redirectTo={`${window.location.origin}/app`}
            localization={{
              variables: {
                sign_in: {
                  email_label: 'Email',
                  password_label: 'Password',
                  email_input_placeholder: 'Enter your email',
                  password_input_placeholder: 'Enter your password',
                  button_label: 'Sign In',
                  loading_button_label: 'Signing in...',
                  social_provider_text: 'Sign in with {{provider}}',
                  link_text: 'Already have an account? Sign in',
                },
                sign_up: {
                  email_label: 'Email',
                  password_label: 'Password',
                  email_input_placeholder: 'Enter your email',
                  password_input_placeholder: 'Enter your password (at least 6 characters)',
                  button_label: 'Sign Up',
                  loading_button_label: 'Signing up...',
                  social_provider_text: 'Sign up with {{provider}}',
                  link_text: "Don't have an account? Sign up",
                },
                forgotten_password: {
                  link_text: 'Forgot your password?',
                  email_label: 'Email',
                  password_label: 'Password',
                  email_input_placeholder: 'Enter your email',
                  button_label: 'Send reset password email',
                  loading_button_label: 'Sending...',
                },
              },
            }}
          />
        </Card>

        <p className="text-center text-sm text-muted-foreground mt-6">
          By signing in, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
};

export default Login;
