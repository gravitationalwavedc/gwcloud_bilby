import { Form } from 'react-bootstrap';

const RadioGroup = ({ title, formik, name, options }) => (
    <>
        <Form.Label>{title}</Form.Label>
        {options.map(({ label, value }) => (
            <Form.Check
                custom
                id={name + label}
                key={name + label}
                label={label}
                type="radio"
                name={name}
                value={value}
                onChange={formik.handleChange}
                checked={formik.values[name] === value}
            />
        ))}
    </>
);

export default RadioGroup;
