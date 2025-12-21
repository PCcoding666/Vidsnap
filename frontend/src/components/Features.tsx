import { MessageSquare, Zap, Search, Mic, Globe, FileText } from "lucide-react";
import { Card } from "@/components/ui/card";

const features = [
  {
    icon: MessageSquare,
    title: "Conversational Video Chat",
    description: "Interact with your videos like talking to a person. Multi-turn dialogue with deep contextual understanding.",
    gradient: "from-blue-500 to-cyan-500"
  },
  {
    icon: Zap,
    title: "Intelligent Summaries",
    description: "One-click generation of multi-level summaries, chapter breakdowns, and keyframe highlights.",
    gradient: "from-purple-500 to-pink-500"
  },
  {
    icon: Search,
    title: "Precision Search",
    description: "Semantic search finds exact moments with timestamped transcript snippets and visual context.",
    gradient: "from-orange-500 to-red-500"
  },
  {
    icon: Mic,
    title: "High-Accuracy Transcription",
    description: "Powered by Paraformer-v2 for >95% accuracy with speaker separation and diarization.",
    gradient: "from-green-500 to-emerald-500"
  },
  {
    icon: Globe,
    title: "Multi-Language Support",
    description: "Break down language barriers with powerful speech recognition across 100+ languages.",
    gradient: "from-indigo-500 to-blue-500"
  },
  {
    icon: FileText,
    title: "Export & Integration",
    description: "Export summaries to Markdown, PDF, or access via JSON API for seamless workflow integration.",
    gradient: "from-violet-500 to-purple-500"
  }
];

const Features = () => {
  return (
    <section id="features" className="py-24 bg-secondary/30">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-4 mb-16 animate-fade-in">
          <h2 className="text-4xl sm:text-5xl font-bold">
            Powerful Features for{" "}
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Video Intelligence
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Everything you need to understand, explore, and extract value from video content
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <Card 
              key={index} 
              className="p-6 hover:shadow-xl transition-all duration-300 hover:-translate-y-1 border-border/50 bg-card/50 backdrop-blur-sm animate-fade-in"
              style={{ animationDelay: `${index * 0.1}s` }}
            >
              <div className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${feature.gradient} mb-4`}>
                <feature.icon className="h-6 w-6 text-white" />
              </div>
              <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
              <p className="text-muted-foreground">{feature.description}</p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;
