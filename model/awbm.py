from __future__ import absolute_import

import jax
import jax.numpy as jnp

from flax import linen as nn
from flax.linen.initializers import constant

class SimplifiedAWBM(nn.Module):
    '''
    This method implements the simplified version of AWBM as explained in:
    
    Towards dynamic catchment modelling: a Bayesian hierarchical mixtures of experts framework
    L. Marshall, D. Nott and A. Sharma
    Hydrological Processes 2007 Vol. 21 Issue 7 Pages 847-861
    DOI: 10.1002/hyp.6294
    https://dx.doi.org/10.1002/hyp.6294
    
    Parameters:
    ----------
    BFI (0-1): Any moisture in excess of the capacity of the surface stores (S_max) is proportioned between 
    surface runoff and baseflow according to the baseflow index (BFI)
    K (0-1): he rate of release of baseflow from the base storage is governed 
    by the baseflow recession constant K
    S_max (Double): Maximum capacity of the surface stores
    S_init (Double <= S_Max): Initial moisture level of the surface store. Must be less than or equal to S_max
        
    '''
    # default model settings
    B_init: float=1
    S_init: float=0.5

    def setup(self) -> None:
        self.BFI = self.param('BFI', constant(0.5), (1,))
        self.K = self.param('K', constant(0.5), (1,))
        self.S_max = self.param('S_max', constant(1), (1,))

    def time_update(self, carry, t_input) -> jnp.ndarray:
        # Get precipitation and evapotranspiration
        precp = t_input[0]
        evap = t_input[1]

        # Update Current Storage moisture
        carry['S_curr'] = nn.relu(carry['S_curr'] + precp - evap)

        carry['S_curr'], carry['B_curr'], outflow, baseflow = jax.lax.cond(
            carry['S_curr'] > carry['S_max'],
            self.excess_fun,
            self.noexcess_fun,
            carry['S_curr'], carry['S_max'], 
            carry['B_curr'], carry['BFI'], carry['K']
        )

        # Calculate total flow
        totalflow = baseflow + outflow

        return carry, totalflow.reshape((1,))
    
    def excess_fun(self, S_curr, S_max, B_curr, BFI, K):
        '''
        Function called when S_cur > S_max
        '''
        excess = S_curr - S_max
        S_curr = S_max
        outflow = (1 - BFI) * excess
        B_curr = B_curr + (BFI * excess)
        baseflow = (1 - K) * B_curr
        B_curr = B_curr - baseflow
        return S_curr, B_curr, outflow, baseflow

    def noexcess_fun(self, S_curr, S_max, B_curr, BFI, K):
        '''
        Function called when S_cur <= S_max
        '''
        outflow = jnp.array(0.0)
        baseflow = B_curr * (1-K)
        B_curr = B_curr - (B_curr*(1-K)) 
        return S_curr, B_curr, outflow, baseflow


    def __call__(self, x) -> jnp.ndarray:
        '''
        Forward pass for the model with the current parameters
        Returns:
        -------
        Outflow (array): Total surface outflow
        Baseflow (array): Total baseflow
        '''
        carry = {
            'S_curr': self.S_init,
            'B_curr': self.B_init,
            'S_max': self.S_max[0],
            'K': self.K[0],
            'BFI': self.BFI[0]
        }

        carry_out, totalflow = jax.lax.scan(self.time_update, carry, x)
        
        return totalflow