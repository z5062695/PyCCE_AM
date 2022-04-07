import collections.abc
import numpy as np
from pycce.bath.array import check_gyro, point_dipole, BathArray, _add_args, _stevens_str_doc
from pycce.bath.map import InteractionMap
from pycce.constants import ELECTRON_GYRO
from pycce.h.total import central_hamiltonian
from pycce.utilities import zfs_tensor, generate_projections, expand, rotate_coordinates, rotate_tensor, outer, \
    normalize


def _attr_arr_setter(self, attr, value, dtype=np.float64):
    if getattr(self, attr) is not None:
        obj = getattr(self, attr)
        obj[...] = np.asarray(value, dtype=dtype)
    else:
        setattr(self, attr, np.asarray(value, dtype=dtype))


class Center:
    r"""
    Class, which contains the properties of the single central spin. Should *not* be initialized directly - use
    ``CenterArray`` instead.

    Args:
        position (ndarray with shape (3, )):
            Cartesian coordinates in Angstrom of the central spin. Default (0., 0., 0.).

        spin (float): Total spin of the central spin.

        D (float or ndarray with shape (3, )): D (longitudinal splitting) parameter of central spin
            in ZFS tensor of central spin in kHz.

            *OR*

            Total ZFS tensor. Default 0.

        E (float): E (transverse splitting) parameter of central spin in ZFS tensor of central spin in kHz.
            Default 0. Ignored if ``D`` is None or tensor.

        gyro (float or ndarray with shape (3, 3))): Gyromagnetic ratio of central spin in rad / ms / G.

            *OR*

            Tensor describing central spin interactions with the magnetic field.

            Default -17608.597050 kHz * rad / G - gyromagnetic ratio of the free electron spin.

        alpha (int or ndarray with shape (2*spin + 1, )):
            :math:`\ket{0}` state of the qubit in :math:`S_z` basis or the index of eigenstate to be used as one.

            Default is **None**.

        beta (int or ndarray with shape (2*spin + 1, )):
            :math:`\ket{1}` state of the qubit in :math:`S_z` basis or the index of eigenstate to be used as one.

            Default is **None**.

        detuning (float): Energy detuning from the zeeman splitting in kHz,
            included as an extra :math:`+\omega \hat S_z` term in the Hamiltonian,
            where :math:`\omega` is the detuning.

            Default 0.
    """

    def __init__(self, position=None,
                 spin=0, D=0, E=0,
                 gyro=ELECTRON_GYRO, alpha=None, beta=None, detuning=0):

        if position is None:
            position = np.array([0, 0, 0])

        self._zfs = None
        self._gyro = None

        self._xyz = None
        self._s = None
        self._h = {}

        self._detuning = None

        self.xyz = position
        self.s = spin
        self.set_zfs(D, E)
        self.set_gyro(gyro)
        self.detuning = detuning

        self.projections_alpha = None
        r"""ndarray with shape (3,): Vector with spin operator matrix elements
        of type :math:`[\bra{0}\hat S_x\ket{0}, \bra{0}\hat S_y\ket{0}, \bra{0}\hat S_z\ket{0}]`, where
        :math:`\ket{0}` is the alpha qubit state. Generated by ``CenterArray``."""
        self.projections_beta = None
        r"""ndarray with shape (3,): Vector with spin operator matrix elements
        of type :math:`[\bra{1}\hat S_x\ket{1}, \bra{1}\hat S_y\ket{1}, \bra{1}\hat S_z\ket{1}]`, where
        :math:`\ket{1}` is the beta qubit state. Generated by ``CenterArray``."""
        # You cannot initialize these from center, only from CenterArray
        self.projections_alpha_all = None
        r"""
        ndarray with shape (2s-1, 3):
            Array of vectors of the central spin matrix elements of form:

            .. math::

                [\bra{0}\hat{S}_x\ket{j}, \bra{0}\hat{S}_y\ket{j}, \bra{0}\hat{S}_z\ket{j}],

            where :math:`\ket{0}` is the alpha qubit state, and :math:`\ket{\j}` are all states.
        """

        self.projections_beta_all = None
        r"""
        ndarray with shape (2s-1, 3):
            Array of vectors of the central spin matrix elements of form:

            .. math::

                [\bra{1}\hat{S}_x\ket{j}, \bra{1}\hat{S}_y\ket{j}, \bra{1}\hat{S}_z\ket{j}],

            where :math:`\ket{1}` is the beta qubit state, and :math:`\ket{\j}` are all states.
        """

        self.energies = None
        """ndarray with shape (2s-1,): Array of the central spin Hamiltonian eigen energies."""
        self.eigenvectors = None
        """ndarray: Eigen states of the central spin Hamiltonian."""

        self.hamiltonian = None
        """Hamiltonian: Central spin Hamiltonian."""

        self._alpha = None
        self._beta = None

        self.alpha_index = None
        """int: Index of the central spin Hamiltonian eigen state, chosen as alpha state of the qubit."""
        self.beta_index = None
        """int: Index of the central spin Hamiltonian eigen state, chosen as beta state of the qubit."""

        self.alpha = alpha
        self.beta = beta

        self._sigma = None

    def get_projections(self, which):
        if which == 'alpha' or which == 1:
            return self.projections_alpha
        elif which == 'beta' or which == 0:
            return self.projections_beta

    def get_projections_all(self, which):
        if which == 'alpha' or which == 1:
            return self.projections_alpha_all
        elif which == 'beta' or which == 0:
            return self.projections_beta_all

    @property
    def xyz(self):
        """ndarray with shape (3, ): Position of the central spin in Cartesian coordinates."""
        return self._xyz

    @xyz.setter
    def xyz(self, position):
        _attr_arr_setter(self, '_xyz', position)

    @property
    def gyro(self):
        """
        ndarray with shape (3,3) or (n,3,3): Tensor describing central spin interactions
            with the magnetic field or array of spins.

            Default -17608.597050 rad / ms / G - gyromagnetic ratio of the free electron spin."""
        gyro, _ = check_gyro(self._gyro)
        return gyro

    @gyro.setter
    def gyro(self, gyro):
        _attr_arr_setter(self, '_gyro', gyro)

    @property
    def zfs(self):
        """ndarray with shape (3,3) or (n,3,3): Zero field splitting tensor of the central spin or array of spins."""
        return self._zfs

    @zfs.setter
    def zfs(self, zfs):
        _attr_arr_setter(self, '_zfs', zfs)

    @property
    def s(self):
        """float or ndarray with shape (n,): Total spin of the central spin or array of spins."""
        return self._s[()]

    @s.setter
    def s(self, spin):
        _attr_arr_setter(self, '_s', spin)

    @property
    def detuning(self):
        """ndarray with shape (3, ): Position of the central spin in Cartesian coordinates."""
        return self._detuning[()]

    @_add_args(_stevens_str_doc)
    @property
    def h(self):
        return self._h

    @detuning.setter
    def detuning(self, detune):
        _attr_arr_setter(self, '_detuning', detune)

    def set_zfs(self, D=0, E=0):
        """
         Set Zero Field Splitting of the central spin from longitudinal ZFS *D* and transverse ZFS *E*.

        Args:
            D (float or ndarray with shape (3, 3)): D (longitudinal splitting) parameter of central spin
                in ZFS tensor of central spin in kHz.

                **OR**

                Total ZFS tensor. Default 0.

            E (float): E (transverse splitting) parameter of central spin in ZFS tensor of central spin in kHz.
                 Default 0. Ignored if ``D`` is None or tensor.
        """

        self.zfs = zfs_tensor(D, E)

    def set_gyro(self, gyro):
        """
        Set gyromagnetic ratio of the central spin.

        Args:
            gyro (float or ndarray with shape (3,3)): Gyromagnetic ratio of central spin in rad / ms / G.

                **OR**

                Tensor describing central spin interactions with the magnetic field.

                Default -17608.597050 kHz * rad / G - gyromagnetic ratio of the free electron spin.

        """
        check = not np.asarray(gyro).shape == (3, 3)
        if check:
            gyro, check = check_gyro(gyro)

            if check:
                gyro = np.eye(3) * gyro

        self._gyro = gyro

    @property
    def alpha(self):
        r"""
        ndarray or int: :math:`\ket{0}` qubit state of the central spin in :math:`S_z` basis

        **OR** index of the energy state to be considered as one.
        """

        return self._get_state('alpha')

    @alpha.setter
    def alpha(self, state):
        self._set_state('alpha', state)

    @property
    def beta(self):
        r"""
        ndarray or int: :math:`\ket{1}` qubit state of the central spin in :math:`S_z` basis

        **OR** index of the energy state to be considered as one.
        """
        return self._get_state('beta')

    @beta.setter
    def beta(self, state):
        self._set_state('beta', state)

    @property
    def dim(self):
        """int or ndarray with shape (n,): Dimensions of the central spin or array of spins."""

        return (self._s * 2 + 1 + 1e-8).astype(int)[()]

    def generate_sigma(self):
        r"""
        Generate Pauli matrices of the qubit in :math:`S_z` basis.
        """
        assert np.isclose(np.inner(self.alpha.conj(), self.beta), 0), \
            f"Pauli matrix can be generated only for orthogonal states, " \
            f"{self.alpha} and {self.beta} are not orthogonal"

        alpha_x_alpha = outer(self.alpha, self.alpha)
        beta_x_beta = outer(self.beta, self.beta)
        alpha_x_beta = outer(self.alpha, self.beta)
        beta_x_alpha = outer(self.beta, self.alpha)

        self._sigma = {'x': alpha_x_beta + beta_x_alpha,
                       'y': -1j * alpha_x_beta + 1j * beta_x_alpha,
                       'z': alpha_x_alpha - beta_x_beta}

    @property
    def sigma(self):
        """
        dict: Dictionary with Pauli matrices of the qubit in :math:`S_z` basis.
        """
        if self._sigma is None:
            self.generate_sigma()
        return self._sigma

    def _set_state(self, name, state):
        if state is not None:
            state = np.asarray(state)
            if state.size == 1:
                setattr(self, name + '_index', int(state))
            else:
                assert state.size == np.prod(self.dim), f"Incorrect format of {name}: {state}"
                setattr(self, '_' + name, normalize(state))

                # remove index if manually set alpha state
                setattr(self, name + '_index', None)
        else:
            setattr(self, '_' + name, state)
        self._sigma = None

    def _get_state(self, name):

        state = getattr(self, '_' + name)
        if state is not None:
            return state

        state = getattr(self, name + '_index')
        if state is not None:
            return state

        return None

    def generate_states(self, magnetic_field=None, bath=None, projected_bath_state=None):
        r"""
        Compute eigenstates of the central spin Hamiltonian.

        Args:
            magnetic_field (ndarray with shape (3,)): Array containing external magnetic field as (Bx, By, Bz).
            bath (BathArray with shape (m,) or ndarray with shape (m, 3, 3):
                Array of all bath spins or array of hyperfine tensors.
            projected_bath_state (ndarray with shape (m,) or (m, 3)):
                Array of :math:`I_z` projections for each bath spin.
        """

        self.generate_hamiltonian(magnetic_field=magnetic_field, bath=bath, projected_bath_state=projected_bath_state)
        self.energies, self.eigenvectors = np.linalg.eigh(self.hamiltonian, UPLO='U')

        if self.alpha_index is not None:
            self._alpha = np.ascontiguousarray(self.eigenvectors[:, self.alpha_index])
        if self.beta_index is not None:
            self._beta = np.ascontiguousarray(self.eigenvectors[:, self.beta_index])

    def __repr__(self):
        message = f"{self.__class__.__name__}" + ("\n(s: " + self.s.__str__() +
                                                  ",\nxyz:\n" + self.xyz.__str__() +
                                                  ",\nzfs:\n" + self.zfs.__str__() +
                                                  ",\ngyro:\n" + self.gyro.__str__())
        if self._detuning.any():
            message += "\ndetuning: " + self.gyro.__str__()
        message += ")"
        return message

    def generate_hamiltonian(self, magnetic_field=None, bath=None, projected_bath_state=None):
        r"""
        Generate central spin Hamiltonian.

        Args:
            magnetic_field (ndarray with shape (3, ) or func):
                Magnetic field of type ``magnetic_field = np.array([Bx, By, Bz])``
                or callable with signature ``magnetic_field(pos)``, where ``pos`` is ndarray with shape (3, ) with the
                position of the spin.

            bath (BathArray with shape (n,) or ndarray with shape (n, 3, 3)):
                Array of bath spins or hyperfine tensors.

            projected_bath_state (ndarray with shape (n, )): :math:`S_z` projections of the bath spin states.

        Returns:
            Hamiltonian: Central spin Hamiltonian, including
                first order contributions from the bath spins.
        """
        if magnetic_field is None:
            magnetic_field = np.array([0., 0., 0.], dtype=np.float64)

        if not callable(magnetic_field):
            magnetic_field = np.asarray(magnetic_field)
            if magnetic_field.size == 1:
                magnetic_field = np.array([0., 0., magnetic_field.reshape(-1)[0]])

        if isinstance(bath, BathArray):
            bath = bath.A
            projected_bath_state = bath.proj

        self.hamiltonian = central_hamiltonian(self, magnetic_field, hyperfine=bath,
                                               bath_state=projected_bath_state)
        return self.hamiltonian

    def transform(self, rotation=None, style='col'):
        """
        Apply coordinate transformation to the central spin.

        Args:
            rotation (ndarray with shape (3, 3)): Rotation matrix.
            style (str): Can be 'row' or 'col'. Determines how rotation matrix is initialized.

        """
        self.xyz = rotate_coordinates(self.xyz, rotation=rotation, style=style)
        self.zfs = rotate_tensor(self.zfs, rotation=rotation, style=style)
        self._gyro = rotate_tensor(self._gyro, rotation=rotation, style=style)
        return


class CenterArray(Center, collections.abc.Sequence):
    r"""
    Class, containing properties of all central spins. The properties of the each separate spin can be accessed
    as elements of the object directly. Each element of the array is an instance of the ``Center`` class.

    Examples:

        Generate array of 2 electron central spins:

        >>> import numpy as np
        >>> ca = CenterArray(2, spin=0.5) # Array of size 2 with spins-1/2
        >>> print(ca)
        CenterArray
        (s: [0.5 0.5],
        xyz:
        [[0. 0. 0.]
         [0. 0. 0.]],
        zfs:
        [[[0. 0. 0.]
          [0. 0. 0.]
          [0. 0. 0.]]
         [[0. 0. 0.]
          [0. 0. 0.]
          [0. 0. 0.]]],
        gyro:
        [[[-17608.59705     -0.          -0.     ]
          [    -0.      -17608.59705     -0.     ]
          [    -0.          -0.      -17608.59705]]
         [[-17608.59705     -0.          -0.     ]
          [    -0.      -17608.59705     -0.     ]
          [    -0.          -0.      -17608.59705]]])

        Set first two eigenstates of the combined central spin Hamiltonian as a singlie qubit state:

        >>> ca.alpha = 0
        >>> ca.beta = 1

        Change gyromagnetic ratio of the first spin:

        >>> ca[0].gyro = np.eye(3) * 1000
        >>> print(ca[0])
        Center
        (s: 0.5,
        xyz:
        [0. 0. 0.],
        zfs:
        [[0. 0. 0.]
         [0. 0. 0.]
         [0. 0. 0.]],
        gyro:
        1000.0)


    Args:
        size (int): Number of central spins.

        spin (ndarray with shape (size,)):
            Total spins of the central spins.

            .. note::

                All center spin properties are broadcasted to the total size of the center array,
                provided by ``size`` argument, or inferred from ``spin``, ``position`` arguments.

        position (ndarray with shape (size, 3)):
            Cartesian coordinates in Angstrom of the central spins. Default (0., 0., 0.).

        D (ndarray with shape (size, ) or ndarray with shape (n, 3, 3)):
            D (longitudinal splitting) parameters of central spins
            in ZFS tensor of central spin in kHz.

            *OR*

            Total ZFS tensor. Default 0.

        E (ndarray with shape (size, )):
            E (transverse splitting) parameters of central spins
            in ZFS tensor of central spin in kHz.
            Default 0. Ignored if ``D`` is None or tensor.

        gyro (ndarray with shape (size, ) or ndarray with shape (size, 3, 3))):
            Gyromagnetic ratios of the central spins in rad / ms / G.

            *OR*

            Tensors describing central spins interactions with the magnetic field.

            Default -17608.597050 kHz * rad / G - gyromagnetic ratio of the free electron spin.

        imap (dict or InteractionMap or ndarray with shape (3, 3)):
            Dict-like object containing interaction tensors between the central spins of the structure {(i, j): T_ij}.
            Where i, j are positional indexes of the central spins. If provided as an ndarray with shape (3, 3),
            assumes the same interactions between all pairs of central spins in the array.
            If provided with shape (size * (size - 1) / 2, 3, 3), assigns the interactions to the ordered pairs:
            ``{(0, 1): imap[0], (0, 2): imap[1] ... (size - 2, size - 1): imap[-1]}``


        alpha (int or ndarray with shape (S, )):
            :math:`\ket{0}` state of the qubit in the product space of all central spins,
            or the index of eigenstate to be used as one.

            Default is **None**.

        beta (int or ndarray with shape (S, )):
            :math:`\ket{1}` state of the qubit in the product space of all central spins,
            or the index of eigenstate to be used as one.

            Default is **None**.

        detuning (ndarray with shape (size, )): Energy detunings from the Zeeman splitting in kHz,
            included as an extra :math:`+\omega \hat S_z` term in the Hamiltonian,
            where :math:`\omega` is the detuning.

            Default is 0.
    """
    def __init__(self, size=None, position=None,
                 spin=None, D=0, E=0,
                 gyro=ELECTRON_GYRO, imap=None,
                 alpha=None,
                 beta=None,
                 detuning=0):

        if size is None:
            if spin is not None:
                spin = np.asarray(spin)
                size = spin.size

            elif position is not None:
                position = np.asarray(position)
                size = position.size // 3

            else:
                raise ValueError('Size of the array is not provided')

        self.size = size

        if position is None:
            position = np.asarray([[0, 0, 0]] * self.size)
        if spin is None:
            spin = 0

        position = np.asarray(position)

        spin = np.asarray(spin).reshape(-1)

        if spin.size != self.size:
            spin = np.array(np.broadcast_to(spin, self.size))

        if position.ndim == 1:
            position = np.array(np.broadcast_to(position, (self.size, position.size)))

        detuning = np.asarray(detuning).reshape(-1)

        if detuning.size != self.size:
            detuning = np.array(np.broadcast_to(detuning, self.size))

        self._state = None
        self.state_index = None

        super().__init__(position=position, spin=spin, D=D, E=E, gyro=gyro, alpha=alpha, beta=beta, detuning=detuning)

        self._array = np.array([Center(position=p, spin=s[..., 0], D=zfs, gyro=g, detuning=d) for p, s, zfs, g, d in
                                zip(self.xyz, self.s[:, np.newaxis], self.zfs, self.gyro, self.detuning)],
                               dtype=object)

        self._h = np.asarray([x.h for x in self._array], dtype=object)

        if isinstance(imap, dict):
            imap = InteractionMap.from_dict(imap)

        if imap is not None and not isinstance(imap, InteractionMap):

            if self.size < 2:
                raise ValueError(f'Cannot assign interaction map for array of size {self.size}')

            imap = np.broadcast_to(imap, (self.size * (self.size - 1) // 2, 3, 3))
            imap = InteractionMap(rows=np.arange(self.size), columns=np.arange(1, self.size), tensors=imap)

        self._imap = imap

        self.energy_alpha = None
        """float: Energy of the alpha state. Generated by ``.generate_projections`` call if ``second_order=True``."""
        self.energy_beta = None
        """float: Energy of the beta state. Generated by ``.generate_projections`` call if ``second_order=True``."""

        self.energies = None
        """ndarray with shape (n, ): Energy of each eingenstate of the central spin Hamiltonian."""

    @property
    def imap(self):
        """
        InteractionMap: dict-like object, which contains interactions between central spins.
        """
        if self._imap is None:
            self._imap = InteractionMap()

        return self._imap

    @property
    def alpha(self):
        r"""
        ndarray or int: :math:`\ket{0}` qubit state of the central spin in :math:`S_z` basis

        **OR** index of the energy state to be considered as one.

        If not provided in the ``CentralArray`` instance, returns the tensor product of all ``alpha`` states of
        each element of the array. If there are undefined ``alpha`` states of the elements of the array,
        raises an error.

        Examples:

            >>> ca = CenterArray(2, spin=0.5) # Array of size 2 with spins-1/2
            >>> ca[0].alpha = [0,1]
            >>> ca[1].alpha = [1,0]
            >>> print(ca.alpha)
            [0.+0.j 0.+0.j 1.+0.j 0.+0.j]

        """

        return self._get_state('alpha')

    @alpha.setter
    def alpha(self, state):
        self._set_state('alpha', state)

    @property
    def beta(self):
        r"""
        ndarray or int: :math:`\ket{1}` qubit state of the central spin in :math:`S_z` basis

        **OR** index of the energy state to be considered as one.
        """
        return self._get_state('beta')

    @beta.setter
    def beta(self, state):
        self._set_state('beta', state)

    @property
    def state(self):
        r"""
        ndarray: Initial state of the qubit in gCCE simulations.
        Assumed to be :math:`\frac{1}{\sqrt{2}}(\ket{0} + \ket{1})` unless provided."""
        state = super(CenterArray, self)._get_state('state')
        if state is not None:
            return state
        else:
            self._check_states()
            return normalize(self.alpha + self.beta)

    @state.setter
    def state(self, state):
        self._set_state('state', state)

    @property
    def gyro(self):
        return self._gyro

    @gyro.setter
    def gyro(self, gyro):
        _attr_arr_setter(self, '_gyro', gyro)

    def __getitem__(self, item):
        newarray = self._array.__getitem__(item)
        if isinstance(newarray, Center):
            return newarray

        else:
            xyz = self.xyz[item]
            gyro = self.gyro[item]
            s = self.s[item]
            zfs = self.zfs[item]
            ca = CenterArray(len(newarray), position=xyz, gyro=gyro, spin=s, D=zfs)
            ca._array = newarray

            if self._imap is not None:
                ca._imap = self.imap.subspace(np.arange(self.size)[item])

            if self.h.any():
                ca._h = self.h[item]

            return ca

    def __setitem__(self, key, val):
        if not isinstance(val, Center):
            raise ValueError

        self.zfs[key] = val.zfs
        self.gyro[key] = val.gyro
        self.s[key] = val.s
        self.xyz[key] = val.xyz

        center = self._array.__getitem__(key)

        center.alpha = val.alpha
        center.beta = val.beta
        center.h.update(val.h)

    def __len__(self):
        return self.size

    def set_zfs(self, D=0, E=0):

        darr = np.asarray(D)

        if darr.shape == (self.size, 3, 3):
            self.zfs = darr

        else:
            if self.zfs is None:
                self.zfs = np.zeros((self.size, 3, 3), dtype=np.float64)

            for i, (d, e) in enumerate(zip(np.broadcast_to(D, self.size), np.broadcast_to(E, self.size))):
                self.zfs[i] = zfs_tensor(d, e)

    def set_gyro(self, gyro):

        garr = np.asarray(gyro)

        if garr.shape == (self.size, 3, 3):
            self.gyro = garr
        else:
            if self.gyro is None:
                self.gyro = np.zeros((self.size, 3, 3), dtype=np.float64)

            for i, g in enumerate(np.broadcast_to(gyro, self.size)):

                g, check = check_gyro(g)

                if check:
                    self._gyro[i] = np.eye(3) * g
                else:
                    self._gyro[i] = g

    def point_dipole(self):
        """
        Using point-dipole approximation, generate interaction tensors between central spins.
        """
        for i in range(self.size):
            for j in range(i + 1, self.size):
                c1 = self[i]
                c2 = self[j]
                self.imap[i, j] = point_dipole(c1.xyz - c2.xyz, c1.gyro, c2.gyro)

    def generate_states(self, magnetic_field=None, bath=None, projected_bath_state=None):

        if isinstance(bath, BathArray):
            projected_bath_state = bath.proj
            bath = bath.A

        for i, c in enumerate(self):
            if bath is None:
                hf = None
            elif len(self) == 1:
                hf = bath
            else:
                hf = bath[..., i, :, :]

            c.generate_states(magnetic_field=magnetic_field,
                              bath=hf, projected_bath_state=projected_bath_state)

        super(CenterArray, self).generate_states(magnetic_field=magnetic_field,
                                                 bath=bath, projected_bath_state=projected_bath_state)
        if self.state_index is not None:
            self._state = np.ascontiguousarray(self.eigenvectors[:, self.state_index])

    def generate_projections(self, second_order=False, level_confidence=0.95):
        r"""
        Generate vectors with the spin projections of the spin states:

            .. math::

                [\bra{a}\hat{S}_x\ket{a}, \bra{a}\hat{S}_y\ket{a}, \bra{a}\hat{S}_z\ket{a}],

        where :math:`\ket{a}` and  is alpha or beta qubit state.
        They are stored in the ``.projections_alpha`` and ``.projections_beta`` respectively.

        If ``second_order`` is set to ``True``, also generates matrix elements of qubit states and all
        other eigenstates of the central spin Hamiltonian, used in computing second order couplings between bath spins:

        .. math::

                [\bra{a}\hat{S}_x\ket{b}, \bra{a}\hat{S}_y\ket{b}, \bra{a}\hat{S}_z\ket{b}],

        where :math:`\ket{a}` is qubit level and :math:`\ket{b}` are all other energy levels.

        This function is called in the ``CCE`` routine.

        .. note::

            if qubit state are not eigenstates and ``second_order`` set to ``True``, for each qubit state finds a close
            eigenstate (with minimal fidelity between two states set by ``level_confidence`` keyword) and uses that
            one instead of user provided.


        Args:
            second_order (bool): True if generate properties, necessary for second order corrections.
            level_confidence (float):
                Minimum fidelity between an eigenstate and provided qubit level for them to be
                considered the same. Used only if ``second_order == True``.

        """
        self._check_states()
        if second_order:
            ai = _close_state_index(self.alpha, self.eigenvectors, level_confidence=level_confidence)
            bi = _close_state_index(self.beta, self.eigenvectors, level_confidence=level_confidence)

            alpha = self.eigenvectors[:, ai]
            beta = self.eigenvectors[:, bi]

            self.energy_alpha = self.energies[ai]
            self.energy_beta = self.energies[bi]

            self.energies = self.energies

            gp = generate_projections
            self.projections_alpha_all = np.array([gp(alpha, s, spins=self.s) for s in self.eigenvectors.T])
            self.projections_beta_all = np.array([gp(beta, s, spins=self.s) for s in self.eigenvectors.T])

            for i, center in enumerate(self):
                center.projections_alpha_all = self.projections_alpha_all[:, i]
                center.projections_beta_all = self.projections_beta_all[:, i]

        else:

            self.energy_alpha = None
            self.energy_beta = None

            self.projections_alpha_all = None
            self.projections_beta_all = None

        self.projections_alpha = np.array(generate_projections(self.alpha, spins=self.s))
        self.projections_beta = np.array(generate_projections(self.beta, spins=self.s))

        for i, center in enumerate(self):
            center.projections_alpha = self.projections_alpha[i]
            center.projections_beta = self.projections_beta[i]

    def get_energy(self, which):
        r"""
        Get energy of the qubit state.

        Args:
            which (str): ``alpha`` for :math:`\ket{0}` qubit state, ``beta`` for :math:`\ket{1}` qubit state.

        Returns:
            float: Energy of the qubit state.
        """
        if which == 'alpha' or which == True:
            return self.energy_alpha
        elif which == 'beta' or which == False:
            return self.energy_beta

    def generate_sigma(self):
        self._check_states()
        super(CenterArray, self).generate_sigma()
        for i, c in enumerate(self):
            if c.alpha is not None and c.beta is not None:
                try:
                    c.generate_sigma()
                    for x in c.sigma:
                        c.sigma[x] = expand(c.sigma[x], i, self.dim)
                except AssertionError:
                    pass

    def _check_states(self):
        for n in ['alpha', 'beta']:
            s = getattr(self, n)
            if s is None or isinstance(s, int):
                raise ValueError(f'Wrong {n} format: {s}')

    def _get_state(self, name):
        state = getattr(self, '_' + name)
        if state is not None:
            return state

        state = getattr(self, name + '_index')
        if state is not None:
            return state

        state = 1
        for c in self:
            s = getattr(c, name)
            if s is None:
                return None
            state = np.kron(state, s)
        state = normalize(state)
        return state

    def add_interaction(self, i, j, tensor):
        """
        Add interactions tensor between bath spins with indexes ``i`` and ``j``.

        Args:
            i (int or ndarray (n,) ):
                Index of the first spin in the pair or array of the indexes of the first spins in n pairs.
            j (int or ndarray with shape (n,)):
                Index of the second spin in the pair or array of the indexes of the second spins in n pairs.
            tensor (ndarray with shape (3,3) or (n, 3,3)):
                Interaction tensor between the spins i and j or array of tensors.
        """

        self.imap[i, j] = tensor

def _close_state_index(state, eiv, level_confidence=0.95):
    r"""
    Get index of the eigenstate stored in eiv,
    which has fidelity higher than ``level_confidence`` with the provided ``state``.

    Args:
        state (ndarray with shape (2s+1,)): State for which to find the analogous eigen state.
        eiv (ndarray with shape (2s+1, 2s+1)): Matrix of eigenvectors as columns.
        level_confidence (float): Threshold fidelity. Default 0.95.

    Returns:
        int: Index of the eigenstate.
    """
    ev_state = eiv.conj().T @ state

    indexes = np.argwhere(ev_state * ev_state.conj() > level_confidence).flatten()

    if not indexes.size:
        raise ValueError(f"Initial qubit state is below F = {level_confidence} "
                         f"to the eigenstate of central spin Hamiltonian.\n"
                         f"Qubit level:\n{repr(state)}\n"
                         f"Eigenstates (rows):\n{repr(eiv.T)}")
    return indexes[0]

# class CenterArray:
#     _dtype_center = np.dtype([('N', np.unicode_, 16),
#                               ('s', np.float64),
#                               ('xyz', np.float64, (3,)),
#                               ('D', np.float64, (3, 3)),
#                               ('gyro', np.float64, (3, 3))])
#
#     def __init__(self, shape=None, position=None,
#                  spin=None, D=None, E=0,
#                  gyro=ELECTRON_GYRO, imap=None):
#
#         if shape is None:
#             raise ValueError('No shape provided')
#
#         self.shape = shape
#         self.size = shape
#
#         self.indexes = np.arange(shape)
#         self.xyz = np.zeros((self.size, 3))
#         self.s = np.zeros(self.size)
#         self.gyro = np.zeros((self.size, 3, 3))
#         self.zfs = np.zeros((self.size, 3, 3))
#
#         self.xyz = position
#         self.spin = spin
#         self.set_gyro(gyro)
#         self.set_zfs(D, E)
#
#         self.imap = imap
#
#         self._state = None
#         self._alpha = None
#         self._beta = None
#
#         self._alpha_list = None
#         self._beta_list = None
#
