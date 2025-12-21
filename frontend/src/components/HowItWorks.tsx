import { Upload, Brain, MessagesSquare } from "lucide-react";

const steps = [
  {
    icon: Upload,
    number: "01",
    title: "Input Your Video",
    description: "Paste a YouTube link or upload a local video file (MP4, AVI, MOV, MKV). Processing starts instantly.",
    color: "text-blue-500"
  },
  {
    icon: Brain,
    number: "02",
    title: "AI Analysis",
    description: "Advanced AI automatically transcribes, extracts keyframes, identifies speakers, and generates comprehensive summaries.",
    color: "text-purple-500"
  },
  {
    icon: MessagesSquare,
    number: "03",
    title: "Interact & Explore",
    description: "Review summaries, search transcripts, or start a conversation with your video. Ask questions and get instant, precise answers.",
    color: "text-pink-500"
  }
];

const HowItWorks = () => {
  return (
    <section id="how-it-works" className="py-24 bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-4 mb-16 animate-fade-in">
          <h2 className="text-4xl sm:text-5xl font-bold">
            How{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              It Works
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Three simple steps to unlock the full potential of your video content
          </p>
        </div>

        <div className="relative max-w-5xl mx-auto">
          {/* Connection lines */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-primary via-accent to-primary opacity-20 transform -translate-y-1/2" />
          
          <div className="grid md:grid-cols-3 gap-8 relative">
            {steps.map((step, index) => (
              <div 
                key={index} 
                className="relative animate-fade-in"
                style={{ animationDelay: `${index * 0.2}s` }}
              >
                <div className="bg-card border border-border/50 rounded-2xl p-8 hover:shadow-xl transition-all duration-300 hover:-translate-y-2">
                  <div className="relative mb-6">
                    <div className={`inline-flex p-4 rounded-2xl bg-gradient-to-br ${step.color === "text-blue-500" ? "from-blue-500 to-cyan-500" : step.color === "text-purple-500" ? "from-purple-500 to-pink-500" : "from-pink-500 to-red-500"}`}>
                      <step.icon className="h-8 w-8 text-white" />
                    </div>
                    <div className="absolute -top-2 -right-2 text-6xl font-bold text-primary/10">
                      {step.number}
                    </div>
                  </div>
                  
                  <h3 className="text-2xl font-semibold mb-3">{step.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="text-center mt-12 animate-fade-in" style={{ animationDelay: "0.6s" }}>
          <p className="text-muted-foreground mb-2">
            <span className="font-semibold text-foreground">Average processing time:</span> Under 30 seconds for a 5-minute video
          </p>
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
