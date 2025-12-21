import { Card } from "@/components/ui/card";
import { Star } from "lucide-react";

const testimonials = [
  {
    name: "Sarah Chen",
    role: "PhD Student",
    content: "VideoChat has revolutionized how I process research videos. What used to take hours now takes minutes. The conversational interface feels magical!",
    rating: 5
  },
  {
    name: "Michael Rodriguez",
    role: "Content Creator",
    content: "Analyzing competitor videos used to be painful. Now I can extract insights, quotes, and strategies in seconds. This tool is a game-changer for my content strategy.",
    rating: 5
  },
  {
    name: "Emily Thompson",
    role: "Product Manager",
    content: "Our team reviews dozens of user interview recordings weekly. VideoChat's speaker diarization and smart search have saved us countless hours. Absolutely essential!",
    rating: 5
  }
];

const Testimonials = () => {
  return (
    <section id="testimonials" className="py-24 bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-4 mb-16 animate-fade-in">
          <h2 className="text-4xl sm:text-5xl font-bold">
            Loved by{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Professionals
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            See what our users have to say about their experience
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {testimonials.map((testimonial, index) => (
            <Card 
              key={index}
              className="p-6 hover:shadow-xl transition-all duration-300 hover:-translate-y-1 border-border/50 bg-card/50 backdrop-blur-sm animate-fade-in"
              style={{ animationDelay: `${index * 0.15}s` }}
            >
              <div className="flex gap-1 mb-4">
                {[...Array(testimonial.rating)].map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                ))}
              </div>
              <p className="text-muted-foreground mb-6 leading-relaxed">"{testimonial.content}"</p>
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-primary to-accent" />
                <div>
                  <div className="font-semibold">{testimonial.name}</div>
                  <div className="text-sm text-muted-foreground">{testimonial.role}</div>
                </div>
              </div>
            </Card>
          ))}
        </div>

        <div className="text-center mt-12 space-y-2 animate-fade-in" style={{ animationDelay: "0.45s" }}>
          <p className="text-muted-foreground">
            <span className="font-semibold text-foreground">50,000+</span> videos processed
          </p>
          <p className="text-muted-foreground">
            <span className="font-semibold text-foreground">125,000+</span> hours saved for our users
          </p>
        </div>
      </div>
    </section>
  );
};

export default Testimonials;
