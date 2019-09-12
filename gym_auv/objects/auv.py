"""
This module implements an AUV that is simulated in the horizontal plane.
"""
import numpy as np
import numpy.linalg as linalg

import gym_auv.utils.constants as const
import gym_auv.utils.geomutils as geom

class AUV2D():
    """
    Creates an environment with a vessel, goal and obstacles.

    Attributes
    ----------
    path_taken : np.array
        Array of size (?, 2) discribing the path the AUV has taken.
    radius : float
        The maximum distance from the center of the AUV to its edge
        in meters.
    t_step : float
        The simulation timestep.
    input : np.array
        The current input. [propeller_input, rudder_position].
    """
    def __init__(self, t_step, init_pos, width=4):
        """
        The __init__ method declares all class atributes.

        Parameters
        ----------
        t_step : float
            The simulation timestep to be used to simulate this AUV.
        init_pos : np.array
            The initial position of the vessel [x, y, psi], where
            psi is the initial heading of the AUV.
        width : float
            The maximum distance from the center of the AUV to its edge
            in meters. Defaults to 2.
        """
        self._state = np.hstack([init_pos, [0, 0, 0]])
        self.prev_states = np.vstack([self._state])
        self.width = width
        self.t_step = t_step
        self.input = [0, 0]
        self.prev_inputs =np.vstack([self.input])

    def step(self, action):
        """
        Steps the vessel self.t_step seconds forward.

        Parameters
        ----------
        action : np.array
            [propeller_input, rudder_position], where
            0 <= propeller_input <= 1 and -1 <= rudder_position <= 1.
        """
        self.input = np.array([_surge(action[0]), _steer(action[1])])
        self._sim()

        self.prev_states = np.vstack([self.prev_states,self._state])
        self.prev_inputs = np.vstack([self.prev_inputs,self.input])

    def _sim(self):
        psi = self._state[2]
        nu = self._state[3:]

        eta_dot = geom.Rzyx(0, 0, geom.princip(psi)).dot(nu)
        nu_dot = const.M_inv.dot(
            const.B(nu).dot(self.input)
            - const.D(nu).dot(nu)
            - const.C(nu).dot(nu)
            - const.L(nu).dot(nu)
        )
        state_dot = np.concatenate([eta_dot, nu_dot])
        self._state += state_dot*self.t_step
        self._state[2] = geom.princip(self._state[2])

    @property
    def position(self):
        """
        Returns an array holding the position of the AUV in cartesian
        coordinates.
        """
        return self._state[0:2]

    @property
    def path_taken(self):
        """
        Returns an array holding the path of the AUV in cartesian
        coordinates.
        """
        return self.prev_states[:, 0:2]

    @property
    def heading(self):
        """
        Returns the heading of the AUV wrt true north.
        """
        return self._state[2]

    @property
    def heading_change(self):
        """
        Returns the change of heading of the AUV wrt true north.
        """
        return geom.princip(self.prev_states[-1, 2] - self.prev_states[-2, 2]) if len(self.prev_states) >= 2 else self.heading

    @property
    def rudder_change(self):
        """
        Returns the smoothed current rutter change.
        """
        sum_rudder_change = 0
        n_samples = min(10, len(self.prev_inputs))
        for i in range(n_samples):
            sum_rudder_change += self.prev_inputs[-1 - i, 1]
        return sum_rudder_change/n_samples

    @property
    def velocity(self):
        """
        Returns the surge and sway velocity of the AUV.
        """
        return self._state[3:5]

    @property
    def speed(self):
        """
        Returns the surge and sway velocity of the AUV.
        """
        return linalg.norm(self.velocity)

    @property
    def yawrate(self):
        """
        Returns the rate of rotation about the z-axis.
        """
        return self._state[5]

    @property
    def max_speed(self):
        """
        Returns the max speed of the AUV.
        """
        return const.MAX_SPEED

    @property
    def crab_angle(self):
        return np.arctan2(self.velocity[1], self.velocity[0])

    @property
    def course(self):
        return self.heading + self.crab_angle


def _surge(surge):
    surge = np.clip(surge, 0, 1)
    return (surge*(const.THRUST_MAX_AUV - const.THRUST_MIN_AUV)
            + const.THRUST_MIN_AUV)

def _steer(steer):
    steer = np.clip(steer, -1, 1)
    return steer*const.RUDDER_MAX_AUV
