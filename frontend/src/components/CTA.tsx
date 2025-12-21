import { Button } from "@/components/ui/button";
import { ArrowRight, Check } from "lucide-react";
import { Link } from "react-router-dom";

const benefits = [
  "No credit card required",
  "5 free videos per month",
  "Cancel anytime",
  "Full feature access"
];

const CTA = () => {
  return (
    <section className="py-24 bg-gradient-to-br from-primary/5 via-accent/5 to-primary/5 relative overflow-hidden">
      <div className="absolute inset-0 bg-grid-pattern opacity-5" />
      <div className="absolute top-1/2 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />
      
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative">
        <div className="max-w-4xl mx-auto text-center space-y-8 animate-fade-in">
          <h2 className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight">
            Ready to Transform Your{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Video Experience?
            </span>
          </h2>
          
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Join thousands of professionals, students, and creators who are saving hours every week with VideoChat
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Button asChild size="lg" className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity shadow-xl shadow-primary/20 text-lg h-14 px-8">
              <Link to="/app">
                Get Started for Free
                <ArrowRight className="ml-2 h-5 w-5" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="text-lg h-14 px-8 border-2 hover:bg-secondary">
              Contact Sales
            </Button>
          </div>

          <div className="flex flex-wrap justify-center gap-x-8 gap-y-3 pt-6">
            {benefits.map((benefit, index) => (
              <div key={index} className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10">
                  <Check className="h-3 w-3 text-primary" />
                </div>
                {benefit}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTA;
