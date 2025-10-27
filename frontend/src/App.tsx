import Header from './components/sections/Header'
import HeroSection from './components/sections/HeroSection'
import PainPoints from './components/sections/PainPoints'
import Features from './components/sections/Features'
import HowItWorks from './components/sections/HowItWorks'
import UseCases from './components/sections/UseCases'
import RealExample from './components/sections/RealExample'
import WhyUs from './components/sections/WhyUs'
import SocialProof from './components/sections/SocialProof'
import CTASection from './components/sections/CTASection'
import Footer from './components/sections/Footer'

function App() {
  return (
    <div className="min-h-screen">
      <Header />
      <HeroSection />
      <PainPoints />
      <Features />
      <HowItWorks />
      <UseCases />
      <RealExample />
      <WhyUs />
      <SocialProof />
      <CTASection />
      <Footer />
    </div>
  )
}

export default App
