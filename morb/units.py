from morb.base import Units, ProxyUnits
from morb import samplers, activation_functions
import theano.tensor as T


class BinaryUnits(Units):
    def sample_from_activation(self, vmap):
        p = activation_functions.sigmoid(vmap[self])
        return samplers.bernoulli(p)
        
    def mean_field_from_activation(self, vmap):
        return activation_functions.sigmoid(vmap[self])

    def free_energy_term_from_activation(self, vmap):
        # softplus of unit activations, summed over # units
        s = - T.nnet.softplus(vmap[self])
        # sum over all but the minibatch dimension
        return T.sum(s, axis=range(1, s.ndim))
  
  
class GaussianPrecisionProxyUnits(ProxyUnits):
    def __init__(self, rbm, units, name=None):
        func = lambda x: x**2 / 2.0
        super(GaussianPrecisionProxyUnits, self).__init__(rbm, units, func, name)
       
class GaussianUnits(Units):
    def __init__(self, rbm, name=None):
        super(GaussianUnits, self).__init__(rbm, name)
        proxy_name = (name + "_precision" if name is not None else None)
        self.precision_units = GaussianPrecisionProxyUnits(rbm, self, name=proxy_name)
        self.proxy_units = [self.precision_units]

    def sample_from_activation(self, vmap):
        return samplers.gaussian(vmap[self])
        
    def mean_field_from_activation(self, vmap):
        return vmap[self]


class LearntPrecisionGaussianProxyUnits(ProxyUnits):
    def __init__(self, rbm, units, name=None):
        func = lambda x: x**2
        super(LearntPrecisionGaussianProxyUnits, self).__init__(rbm, units, func, name)
             
class LearntPrecisionGaussianUnits(Units):
    def __init__(self, rbm, name=None):
        super(LearntPrecisionGaussianUnits, self).__init__(rbm, name)
        proxy_name = (name + "_precision" if name is not None else None)
        self.precision_units = LearntPrecisionGaussianProxyUnits(rbm, self, name=proxy_name)
        self.proxy_units = [self.precision_units]

    def sample_from_activation(self, vmap):
        a1 = vmap[self]
        a2 = vmap[self.precision_units]
        return samplers.gaussian(a1/(-2*a2), 1/(-2*a2))
        
    def sample(self, vmap):
        a1 = self.activation(vmap)
        a2 = self.precision_units.activation(vmap)
        return self.sample_from_activation({ self: a1, self.precision_units: a2 })
        
        
       
# TODO later: gaussian units with custom fixed variance (maybe per-unit). This probably requires two proxies.

class SoftmaxUnits(Units):
    # 0 = minibatches
    # 1 = units
    # 2 = states
    def sample_from_activation(self, vmap):
        p = activation_functions.softmax(vmap[self])
        return samplers.multinomial(p)


class SoftmaxWithZeroUnits(Units):
    """
    Like SoftmaxUnits, but in this case a zero state is possible, yielding N+1 possible states in total.
    """
    def sample_from_activation(self, vmap):
        p0 = activation_functions.softmax_with_zero(vmap[self])
        s0 = samplers.multinomial(p0)
        s = s0[:, :, :-1] # chop off the last state (zero state)
        return s


class TruncatedExponentialUnits(Units):
    def sample_from_activation(self, vmap):
        return samplers.truncated_exponential(-vmap[self]) # lambda = -activation!
        
    def mean_field_from_activation(self, vmap):
        return samplers.truncated_exponential_mean(-vmap[self])



class ExponentialUnits(Units):
    def sample_from_activation(self, vmap):
        return samplers.exponential(-vmap[self]) # lambda = -activation!
        
    def mean_field_from_activation(self, vmap):
        return 1.0 / (-vmap[self])
        
        

class NRELUnits(Units):
    """
    Noisy rectified linear units from 'Rectified Linear Units Improve Restricted Boltzmann Machines'
    by Nair & Hinton (ICML 2010)
    
    WARNING: computing the energy or free energy of a configuration does not have the same semantics
    as usual with NReLUs, because each ReLU is actually the sum of an infinite number of Bernoulli
    units with offset biases. The energy depends on the individual values of these Bernoulli units,
    whereas only the sum is ever sampled (approximately).
    
    See: http://metaoptimize.com/qa/questions/8524/energy-function-of-an-rbm-with-noisy-rectified-linear-units-nrelus
    """
    def sample_from_activation(self, vmap):
        s = a + samplers.gaussian(0, T.nnet.sigmoid(vmap[self])) # approximation: linear + gaussian noise
        return T.max(0, s) # rectify
        
    def mean_field_from_activation(self, vmap):
        return T.max(0, vmap[self])
    
        
        
        
class GammaLogProxyUnits(ProxyUnits):
    def __init__(self, rbm, units, name=None):
        func = lambda x: T.log(x)
        super(GammaLogProxyUnits, self).__init__(rbm, units, func, name)
             
class GammaUnits(Units):
    """
    Two-parameter gamma distributed units, using an approximate sampling procedure for speed.
    The activations should satisfy some constraints:
    - the activation of the GammaUnits should be strictly negative.
    - the activation of the GammaLogProxyUnits should be strictly larger than -1.
    It is recommended to use a FixedBiasParameters instance for the GammaLogProxyUnits,
    so that the 'remaining' part of the activation should be strictly positive. This
    constraint is much easier to satisfy.
    """
    def __init__(self, rbm, name=None):
        super(GammaUnits, self).__init__(rbm, name)
        proxy_name = (name + "_log" if name is not None else None)
        self.log_units = GammaLogProxyUnits(rbm, self, name=proxy_name)
        self.proxy_units = [self.log_units]

    def sample_from_activation(self, vmap):
        a1 = vmap[self]
        a2 = vmap[self.log_units]
        return samplers.gamma_approx(a2 + 1, -1 / a1)
        
    def sample(self, vmap):
        a1 = self.activation(vmap)
        a2 = self.log_units.activation(vmap)
        return self.sample_from_activation({ self: a1, self.log_units: a2 })




class SymmetricBinaryProxyUnits(ProxyUnits):
    def __init__(self, rbm, units, name=None):
        func = lambda x: 1 - x # flip
        super(SymmetricBinaryProxyUnits, self).__init__(rbm, units, func, name)


class SymmetricBinaryUnits(Units):
    """
    Symmetric binary units can be used to include both x and (1 - x) in the energy
    function. This is useful in cases where parameters have to be constrained to
    yield valid conditional distributions. Making the energy function symmetric
    allows for these constraints to be much weaker. For more info, refer to
    http://metaoptimize.com/qa/questions/9628/symmetric-energy-functions-for-rbms
    and the paper referenced there.
    """
    def __init__(self, rbm, name=None):
        super(SymmetricBinaryUnits, self).__init__(rbm, name)
        proxy_name = (name + '_flipped' if name is not None else None)
        self.flipped_units = SymmetricBinaryProxyUnits(rbm, self, name=proxy_name)
        self.proxy_units = [self.flipped_units]
        
    def sample_from_activation(self, vmap):
        p = activation_functions.sigmoid(vmap[self] - vmap[self.flipped_units])
        return samplers.bernoulli(p)
        
    def mean_field_from_activation(self, vmap):
        return activation_functions.sigmoid(vmap[self] - vmap[self.flipped_units])

    def free_energy_term_from_activation(self, vmap):
        # softplus of unit activations, summed over # units
        s = - T.nnet.softplus(vmap[self] - vmap[self.flipped_units])
        # sum over all but the minibatch dimension
        return T.sum(s, axis=range(1, s.ndim))

