import { Clock, BookOpen, Lightbulb, TrendingUp } from "lucide-react";

const benefits = [
  {
    icon: Clock,
    title: "Save Massive Time",
    stat: "70%",
    description: "Reduce video watching time by extracting key information instantly"
  },
  {
    icon: BookOpen,
    title: "Learn Faster",
    stat: "3x",
    description: "Boost learning efficiency with AI-powered summaries and Q&A"
  },
  {
    icon: Lightbulb,
    title: "Never Miss Insights",
    stat: "100%",
    description: "Capture every important detail with precise transcription and search"
  },
  {
    icon: TrendingUp,
    title: "Accelerate Research",
    stat: "5x",
    description: "Analyze competitor content and gather insights at unprecedented speed"
  }
];

const Benefits = () => {
  return (
    <section className="py-24 bg-gradient-to-b from-secondary/30 to-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-4 mb-16 animate-fade-in">
          <h2 className="text-4xl sm:text-5xl font-bold">
            Transform How You{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Consume Video
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Join thousands who have revolutionized their video workflow
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
          {benefits.map((benefit, index) => (
            <div
              key={index}
              className="relative group animate-fade-in"
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className="absolute inset-0 bg-gradient-to-br from-primary/20 to-accent/20 rounded-2xl blur-xl group-hover:blur-2xl transition-all duration-300 opacity-0 group-hover:opacity-100" />
              <div className="relative bg-card border border-border/50 rounded-2xl p-6 text-center hover:shadow-xl transition-all duration-300">
                <div className="inline-flex p-3 rounded-xl bg-gradient-to-br from-primary to-accent mb-4">
                  <benefit.icon className="h-6 w-6 text-white" />
                </div>
                <div className="text-4xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent mb-2">
                  {benefit.stat}
                </div>
                <h3 className="text-lg font-semibold mb-2">{benefit.title}</h3>
                <p className="text-sm text-muted-foreground">{benefit.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Benefits;
