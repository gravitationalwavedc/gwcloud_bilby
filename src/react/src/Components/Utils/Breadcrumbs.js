import React from "react";
import {Breadcrumb, Grid} from "semantic-ui-react";
import { Link } from "found";


class Breadcrumbs extends React.Component {
    constructor(props) {
        super(props);
        if (this.props.paths) {
            this.crumbs = this.props.paths.map(({name, path}, index, {length}) => 
                <React.Fragment key={name}>
                    <Breadcrumb.Divider icon='right chevron'/>
                    <Breadcrumb.Section>
                    {
                        index === length ?
                            <Link to={path} match={this.props.match} router={this.props.router}>
                                {name}
                            </Link>
                        : name
                    }
                    </Breadcrumb.Section>
                </React.Fragment>
            )
        } else {
            this.crumbs = []
        }

        this.crumbs.unshift(
            <React.Fragment key={'home'}>
                    <Link to={'/bilby'} match={this.props.match} router={this.props.router}>
                <Breadcrumb.Section>
                        Bilby Home
                </Breadcrumb.Section>
                    </Link>
            </React.Fragment>
        )
    }


    render() {
        return (
            <Grid>
                {/* <Grid.Row> */}
                    <Breadcrumb size={this.props.size}>
                        {this.crumbs}
                    </Breadcrumb>
                {/* </Grid.Row> */}
            </Grid>
        )
    }
}

export default Breadcrumbs;